import logging
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class VectorSearcher:
    """
    Classe para busca vetorial usando embeddings e FAISS.

    Funcionalidades:
    - Carregar um modelo de embeddings (SentenceTransformer).
    - Construir um índice FAISS de documentos ou trechos.
    - Adicionar novos documentos (texto) ao índice, armazenar seus embeddings.
    - Fazer buscas semânticas: dado um query, gerar embedding e recuperar os k mais similares.

    Observação:
    - Aqui mantemos tudo em memória. Para persistência, precisaria salvar o índice FAISS em disco.
    - Cada documento será armazenado em self.docs_map como um dict ou texto.
    - IDs dos documentos serão simplesmente o índice no self.docs_map.
    - Em um sistema real, você pode armazenar IDs ou metadados mais ricos.
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        logger.info("Carregando modelo de embeddings...")
        self.model = SentenceTransformer(model_name)
        logger.info(f"Modelo de embeddings '{model_name}' carregado com sucesso.")

        self.index = None
        self.docs_map = []
        self.dimension = None  # será definido após gerar o primeiro embedding

    def build_index(self, texts: list):
        """
        Constrói o índice a partir de uma lista de textos.
        Esta função sobrescreve qualquer índice existente.
        """
        if not texts:
            logger.warning("Nenhum documento fornecido para build_index.")
            self.index = None
            self.docs_map = []
            return

        logger.info(f"Gerando embeddings para {len(texts)} documentos...")
        embeddings = self.model.encode(texts, convert_to_numpy=True)

        # Definir a dimensão dos embeddings
        self.dimension = embeddings.shape[1]

        # Criar o índice FAISS
        logger.info("Construindo índice FAISS...")
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(embeddings.astype('float32'))

        # Mapeamento id->doc
        self.docs_map = texts
        logger.info("Índice FAISS construído com sucesso.")

    def add_documents(self, new_texts: list):
        """
        Adiciona novos documentos ao índice existente.
        Se o índice não existir, cria um novo.
        """
        if not new_texts:
            logger.debug("Nenhum documento fornecido em add_documents.")
            return

        embeddings = self.model.encode(new_texts, convert_to_numpy=True)

        if self.index is None:
            # criar um novo índice
            logger.info("Índice inexistente, criando novo índice com os documentos fornecidos.")
            self.dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatL2(self.dimension)
            self.index.add(embeddings.astype('float32'))
            self.docs_map = new_texts
        else:
            # verificar se a dimensão bate
            if embeddings.shape[1] != self.dimension:
                logger.error("A dimensão dos novos embeddings não bate com a dimensão do índice existente.")
                return
            self.index.add(embeddings.astype('float32'))
            self.docs_map.extend(new_texts)

        logger.info(f"{len(new_texts)} documentos adicionados ao índice vetorial.")

    def search(self, query: str, top: int = 5) -> list:
        """
        Faz uma busca semântica por query e retorna os textos dos documentos mais similares.
        Caso o índice esteja vazio ou não exista, retorna lista vazia.
        """
        if self.index is None or len(self.docs_map) == 0:
            logger.warning("Índice vazio ou não inicializado. Retornando lista vazia.")
            return []

        # Gerar embedding da query
        q_embed = self.model.encode([query], convert_to_numpy=True).astype('float32')
        D, I = self.index.search(q_embed, top)

        # I é uma matriz [1, top] com índices dos docs mais similares
        # Se quiser também distâncias, D as contém.
        results = []
        for idx in I[0]:
            if 0 <= idx < len(self.docs_map):
                results.append(self.docs_map[idx])

        return results

    def get_document_by_id(self, doc_id: int):
        """
        Retorna o documento original pelo ID interno.
        Isso é opcional, depende de como você gerencia doc_id.
        """
        if 0 <= doc_id < len(self.docs_map):
            return self.docs_map[doc_id]
        return None

    def save_index(self, path: str):
        """
        Salva o índice FAISS em disco.
        Também seria preciso salvar self.docs_map separadamente (ex: em JSON).
        """
        if self.index is not None:
            faiss.write_index(self.index, path)
            logger.info(f"Índice FAISS salvo em {path}.")
        else:
            logger.warning("Nenhum índice para salvar.")

    def load_index(self, path: str, docs_map_path: str = None):
        """
        Carrega o índice FAISS de disco.
        Também seria preciso carregar docs_map de um JSON (caso docs_map_path seja fornecido).
        """
        if not os.path.exists(path):
            logger.error(f"Índice {path} não encontrado.")
            return
        self.index = faiss.read_index(path)
        # Carregar docs_map se tiver docs_map_path
        if docs_map_path and os.path.exists(docs_map_path):
            import json
            with open(docs_map_path, 'r') as f:
                self.docs_map = json.load(f)
            # Dimension pode ser inferida do índice
            if self.index and self.index.is_trained:
                self.dimension = self.index.d
        logger.info("Índice FAISS carregado com sucesso.")