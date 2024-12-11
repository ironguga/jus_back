import logging
import os
import json
from pathlib import Path
from typing import List, Dict, Optional

import asyncio
from dotenv import load_dotenv

from utils.transcribe import AudioProcessor
from utils.image_processor import ImageProcessor
from utils.document_processor import DocumentProcessor
from utils.video_processor import VideoProcessor
from utils.path_manager import PathManager
from utils.azure_integration import azure_gpt_chat_completion
from utils.summarizer import Summarizer

logger = logging.getLogger(__name__)
load_dotenv()

class DocumentMCPServer:
    """
    O MCP Server coordena o processamento de diferentes tipos de arquivos (áudio, imagem, documento, vídeo)
    e também lida com consultas. Antes ele apenas chamava `azure_gpt_chat_completion` após pegar o contexto.

    Agora, `process_query` pode receber um contexto já construído (sumários de vários docs, etc.)
    e se necessário pode resumir novamente esse contexto antes de enviar para o modelo.

    Também podemos armazenar aqui, se necessário, informações sobre quantos documentos temos, etc.
    Mas assumimos que o main.py faz a maior parte da lógica, e aqui apenas finalizamos a chamada ao modelo.
    """

    def __init__(self):
        self.audio_processor = AudioProcessor()
        self.image_processor = ImageProcessor()
        self.document_processor = DocumentProcessor()
        self.video_processor = VideoProcessor()
        self._initialized = False

        # Instancia o summarizer para uso interno
        self.summarizer = Summarizer()

    async def initialize(self):
        """Inicializa o MCP Server"""
        try:
            logger.info("Inicializando MCP Server...")
            PathManager.initialize()
            await self.document_processor.initialize()
            await self.image_processor.initialize()
            self._initialized = True
            logger.info("MCP Server inicializado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao inicializar MCP Server: {e}")
            raise

    async def close(self):
        """Fecha conexões do MCP Server se necessário"""
        pass

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcreve áudios usando Whisper (já implementado)."""
        try:
            logger.info(f"Transcrevendo áudio: {file_path}")
            text = await self.audio_processor.process(file_path)
            return text
        except Exception as e:
            logger.error(f"Erro na transcrição do áudio: {e}")
            raise

    async def process_audio(self, file_path: str, file_name: str):
        """Processa arquivo de áudio (transcreve)."""
        text = await self.transcribe_audio(file_path)
        return text

    async def process_image(self, file_path: str, file_name: str):
        """Processa imagem extraindo texto via OCR."""
        text = await self.image_processor.process(file_path)
        return text

    async def process_document(self, file_path: str, file_name: str):
        """Processa documento extraindo texto."""
        text = await self.document_processor.process(file_path)
        return text

    async def process_video(self, file_path: str, file_name: str):
        """Processa vídeo extraindo texto relevante."""
        text = await self.video_processor.process(file_path)
        return text

    async def process_query(self, query: str, historico: List[Dict], contexto: str = "") -> str:
        """
        Processa a consulta do usuário. Agora mais flexível:
        
        - Recebe 'query' do usuário.
        - Recebe 'historico' (últimas mensagens) para manter contexto conversacional.
        - Recebe um 'contexto' já preparado pelo main.py (por exemplo, sumários de diversos docs).
        
        O trabalho do MCP aqui é:
        1. Verificar se o _initialized está True.
        2. Se o contexto estiver muito grande, resumi-lo usando o summarizer.
        3. Chamar azure_gpt_chat_completion(query, contexto, historico) para obter a resposta.
        4. Se necessário, pode fazer chamadas intermediárias de sumarização.
        """

        if not self._initialized:
            return "O servidor não foi inicializado corretamente."

        # Se o contexto for muito grande, resumir novamente
        # Podemos definir um limite de caracteres, por exemplo 8000 chars
        if contexto and len(contexto) > 8000:
            logger.info("Contexto muito grande, resumindo antes de enviar ao modelo...")
            contexto = self.summarizer.summarize(contexto, max_length=300)
            logger.debug(f"Contexto resumido para {len(contexto)} caracteres.")

        # Agora chamamos o modelo
        # historico já está limitado no main.py, mas se quiser pode resumir aqui também
        # Caso queira resumir o histórico, pode fazê-lo aqui:
        # se a soma dos conteúdos do historico for muito grande, sumarizar o historico
        total_hist_length = sum(len(m['content']) for m in historico)
        if total_hist_length > 4000:
            # Concatena histórico para sumário
            hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in historico)
            hist_sum = self.summarizer.summarize(hist_text, max_length=200)
            # Cria um novo historico resumido
            historico = [{"role": "system", "content": f"Resumo da conversa até agora: {hist_sum}"}]

        # Chama o modelo final
        try:
            resposta = await azure_gpt_chat_completion(query, contexto, historico)
            return resposta.strip()
        except Exception as e:
            logger.error(f"Erro ao consultar Azure GPT: {e}")
            return f"Erro ao processar consulta: {str(e)}"