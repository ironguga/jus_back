# utils/mcp_server.py
import logging
import os
import asyncio
from pathlib import Path
from typing import List
import sqlite3

from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from dotenv import load_dotenv

# Aqui não utilizamos vector_index ou sumarização, pois vamos enviar tudo
# diretamente ao modelo. Caso queira manter sumarização, pode fazê-lo,
# porém não faremos filtragem, retornaremos todos os documentos.

load_dotenv()
logger = logging.getLogger(__name__)

class DocumentMCPServer:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY não configurada")
        self._initialized = False

        # Processadores serão injetados no startup
        self.document_processor = None
        self.image_processor = None
        self.video_processor = None
        self.audio_processor = None

    async def initialize(self):
        logger.info("Inicializando MCP Server...")
        docs = await self.db_manager.list_all_processed_documents()

        if not docs or len(docs) == 0:
            logger.warning("Nenhum documento processado encontrado.")
        else:
            logger.info(f"{len(docs)} documentos disponíveis para análise.")

        self._initialized = True
        logger.info("MCP Server inicializado com sucesso.")

    async def process_query(self, query: str) -> str:
        try:
            if not self._initialized:
                return "O servidor não foi inicializado corretamente."

            # Obtém todos os documentos sem filtragem
            all_docs = await self.db_manager.list_all_processed_documents()

            if not all_docs:
                # Caso não haja docs
                full_prompt = f"""{HUMAN_PROMPT}Você é um assistente amigável e útil.
Não há documentos disponíveis.

Pergunta do usuário:
{query}

Responda de forma útil, mesmo sem documentos, ou diga que não encontrou nada.
{AI_PROMPT}"""
            else:
                # Constrói o contexto com todos os documentos
                # Se o número de docs e tamanho for muito grande, isso pode estourar o contexto do modelo
                contexto = "\n\n".join([
                    f"[Documento #{doc['id']} - {doc['file_name']} ({doc['file_type']}): {doc['content']}"
                    for doc in all_docs
                ])

                full_prompt = f"""{HUMAN_PROMPT}Você é um assistente amigável, útil e especialista em analisar documentos.
Você tem acesso a todos os documentos a seguir:

{contexto}

Você pode usar todo o conteúdo desses documentos para responder à pergunta do usuário. Seja específico, contextual, cite as fontes ([Documento #id]) conforme necessário. Mantenha o tom amigável e conversacional, e responda em português.

Pergunta do usuário:
{query}{AI_PROMPT}"""

            response = await asyncio.to_thread(
                self.anthropic.completions.create,
                model="claude-2",
                max_tokens_to_sample=1024,
                prompt=full_prompt
            )

            return response.completion.strip()

        except Exception as e:
            logger.error(f"Erro processando query: {e}")
            return f"Erro ao processar consulta: {str(e)}"

    async def close(self):
        pass