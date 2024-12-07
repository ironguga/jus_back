import sqlite3
import logging
from pathlib import Path
from typing import Dict, List
import os
import asyncio
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class DocumentMCPServer:
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY não configurada")
        self._initialized = False

    async def initialize(self):
        logger.info("Inicializando MCP Server...")
        self._initialized = True
        logger.info("MCP Server inicializado com sucesso.")

    async def process_query(self, query: str) -> str:
        """Processa a query usando Anthropic e retorna a resposta do modelo."""
        try:
            # Caminho para o banco de dados
            db_path = Path(__file__).parents[1] / "database" / "banco.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Contagem de documentos por tipo
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN file_type = 'audio' THEN 1 ELSE 0 END) as audios,
                    SUM(CASE WHEN file_type = 'image' THEN 1 ELSE 0 END) as fotos,
                    SUM(CASE WHEN file_type = 'video' THEN 1 ELSE 0 END) as videos,
                    SUM(CASE WHEN file_type = 'document' THEN 1 ELSE 0 END) as docs
                FROM processed_content
            """)
            stats = cursor.fetchone()
            total, audios, fotos, videos, docs = stats if stats else (0,0,0,0,0)

            # Busca todos os documentos processados
            cursor.execute("""
                SELECT id, file_name, file_type, content 
                FROM processed_content 
                ORDER BY id
            """)
            documentos = cursor.fetchall()
            conn.close()

            # Descrição dos tipos de documentos disponíveis
            tipos_desc = []
            if audios > 0: tipos_desc.append(f"{audios} transcrições de áudio")
            if fotos > 0: tipos_desc.append(f"{fotos} textos extraídos de imagens")
            if videos > 0: tipos_desc.append(f"{videos} transcrições de vídeo")
            if docs > 0: tipos_desc.append(f"{docs} documentos")

            if len(tipos_desc) > 1:
                tipos_str = ", ".join(tipos_desc[:-1]) + " e " + tipos_desc[-1]
            elif tipos_desc:
                tipos_str = tipos_desc[0]
            else:
                tipos_str = "nenhum documento disponível"

            # Contexto com o conteúdo dos documentos
            contexto = "\n\n".join([
                f"[Documento #{doc[0]} - {doc[1]} ({doc[2]})]: {doc[3]}"
                for doc in documentos
            ])

            full_prompt = f"""{HUMAN_PROMPT}Você é um assistente amigável especializado em análise de conversas e documentos.
Você tem acesso a {total} documentos, incluindo {tipos_str}.

Aqui está o conteúdo dos documentos:
{contexto}

Lembre-se:
1. Mantenha o contexto da conversa atual
2. Se houver referência a algo discutido antes, use esse contexto
3. Identifique sempre: remetente, destinatário, tipo de conversa e canal
4. Cite as fontes naturalmente
5. Seja amigável e conversacional
6. Responda em português

{query}{AI_PROMPT}"""

            # Chamada síncrona da Anthropic usando executor assíncrono
            response = await asyncio.to_thread(
                self.anthropic.completions.create,
                model="claude-2",
                max_tokens_to_sample=1024,
                prompt=full_prompt
            )

            return response.completion.strip()

        except Exception as e:
            logger.error(f"Erro processando query: {e}")
            raise

    async def search_documents(self, query_info: str) -> List[Dict]:
        return []

    async def extract_relevant_context(self, documents: List[Dict], query: str) -> str:
        return ""

    async def generate_response(self, context: str, query: str) -> str:
        return context

    async def close(self):
        pass