import faiss
import numpy as np
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class VectorIndex:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        logger.info("Carregando modelo de embeddings...")
        self.model = SentenceTransformer(model_name)
        logger.info("Modelo de embeddings carregado.")
        self.index = None
        self.docs_map = []

    def build_index(self, docs):
        """docs é uma lista de dicionários com 'id' e 'content'."""
        if not docs:
            logger.warning("Nenhum documento disponível para indexação. Índice não será criado.")
            self.index = None
            self.docs_map = []
            return

        texts = [d['content'] for d in docs if d['content'] and d['content'].strip()]
        if len(texts) == 0:
            logger.warning("Nenhum texto válido para criar embeddings. Índice não será criado.")
            self.index = None
            self.docs_map = []
            return

        embeddings = self.model.encode(texts, convert_to_numpy=True)
        # Verifica se embeddings é vazio ou tem dimensões inesperadas
        if embeddings.size == 0 or embeddings.ndim < 2:
            logger.warning("Embeddings vazios ou inválidos. Índice não será criado.")
            self.index = None
            self.docs_map = []
            return

        # Agora embeddings tem pelo menos 2D
        if embeddings.shape[0] == 0:
            logger.warning("Nenhum embedding gerado. Índice não será criado.")
            self.index = None
            self.docs_map = []
            return

        # Criação do índice FAISS
        self.index = faiss.IndexFlatL2(embeddings.shape[1])
        self.index.add(embeddings.astype('float32'))

        # Mapeamos apenas os docs que realmente tiveram conteúdo
        valid_docs = []
        count = 0
        for d in docs:
            if d['content'] and d['content'].strip():
                valid_docs.append(d)
        self.docs_map = valid_docs

        logger.info("Índice FAISS construído com sucesso")

    def search(self, query, top_k=5):
        # Se o índice não existe ou sem docs, retorna vazio
        if self.index is None or len(self.docs_map) == 0:
            logger.warning("Índice vazio ou sem documentos. Retornando lista vazia.")
            return []
        q_embed = self.model.encode([query], convert_to_numpy=True).astype('float32')
        D, I = self.index.search(q_embed, top_k)
        results = []
        for idx in I[0]:
            if 0 <= idx < len(self.docs_map):
                results.append(self.docs_map[idx])
        return results

    def embed_text(self, text):
        return self.model.encode([text], convert_to_numpy=True)[0]