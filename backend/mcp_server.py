import json
import logging
import uuid
import hashlib
import shutil
import os
from pathlib import Path

from utils.transcribe import AudioProcessor
from utils.image_processor import ImageProcessor
from utils.document_processor import DocumentProcessor
from utils.video_processor import VideoProcessor
from utils.path_manager import PathManager

logger = logging.getLogger(__name__)

class DocumentMCPServer:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.audio_processor = AudioProcessor()
        self.image_processor = ImageProcessor()
        self.document_processor = DocumentProcessor()
        self.video_processor = VideoProcessor()
        
    async def initialize(self):
        """Inicializa o MCP Server"""
        try:
            logger.info("Inicializando MCP Server...")
            
            # Inicializa os diretórios
            PathManager.initialize()
            
            # Inicializa os processadores
            await self.document_processor.initialize()
            await self.image_processor.initialize()
            
            self._initialized = True
            logger.info("MCP Server inicializado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao inicializar MCP Server: {e}")
            raise

    async def transcribe_audio(self, file_path: str) -> str:
        try:
            logger.info(f"Transcrevendo áudio: {file_path}")
            text = await self.audio_processor.process(file_path)
            return text
        except Exception as e:
            logger.error(f"Erro na transcrição do áudio: {e}")
            raise

    async def process_audio(self, file_path: str, file_name: str):
        """Processa arquivo de áudio"""
        try:
            logger.info(f"Iniciando transcrição do áudio: {file_name}")
            text = await self.transcribe_audio(file_path)
            
            if not text or not text.strip():
                raise ValueError("Texto transcrito vazio")
                
            # Salva no banco
            await self.db_manager.save_processed_content({
                "type": "audio",
                "content": text,
                "metadata": {
                    "file_name": file_name,
                    "file_type": "audio",
                    "processed": True
                }
            })
            logger.info(f"Conteúdo do áudio salvo no banco: {file_name}")
            
            # Move arquivo
            processed_path = PathManager.get_processed_path(file_name)
            os.rename(file_path, str(processed_path))
            logger.info(f"Áudio movido para processados: {processed_path}")
            
        except Exception as e:
            logger.error(f"Erro processando áudio {file_name}: {e}")
            if os.path.exists(file_path):
                unprocessed_path = PathManager.get_unprocessed_path(file_name)
                os.rename(file_path, str(unprocessed_path))
                logger.info(f"Áudio movido para não processados: {unprocessed_path}")
            raise

    async def process_image(self, file_path: str, file_name: str):
        """Processa imagem usando OCR"""
        try:
            # Extrai texto da imagem
            text = await self.image_processor.process(file_path)
            
            # Mesmo que não encontre texto, salva os metadados
            metadata = {
                "file_name": file_name,
                "file_type": "image",
                "processed": True,
                "size": os.path.getsize(file_path),
                "dimensions": await self.image_processor.get_dimensions(file_path)
            }

            # Salva no banco mesmo se não tiver texto
            await self.db_manager.save_processed_content({
                "type": "image",
                "content": text or "Nenhum texto encontrado na imagem",
                "metadata": metadata
            })

            # Move para processados
            processed_path = PathManager.get_processed_path(file_name)
            os.rename(file_path, str(processed_path))
            logger.info(f"Imagem processada com sucesso: {file_name}")

        except Exception as e:
            logger.error(f"Erro no processamento da imagem: {e}")
            if os.path.exists(file_path):
                unprocessed_path = PathManager.get_unprocessed_path(file_name)
                os.rename(file_path, str(unprocessed_path))
                logger.info(f"Arquivo movido para não processados: {unprocessed_path}")
            raise

    async def process_document(self, file_path: str, file_name: str):
        """Processa documento baseado em sua extensão"""
        try:
            extension = Path(file_name).suffix.lower()
            text = await self.document_processor.process(file_path)
            
            if not text or not text.strip():
                raise ValueError(f"Texto extraído vazio do documento: {file_name}")
            
            # Prepara metadados específicos por tipo
            metadata = {
                "file_name": file_name,
                "file_type": extension[1:],  # Remove o ponto
                "processed": True,
                "size": os.path.getsize(file_path)
            }
            
            # Salva no banco
            await self.db_manager.save_processed_content({
                "type": "document",
                "content": text,
                "metadata": metadata
            })
            
            # Move para processados
            processed_path = PathManager.get_processed_path(file_name)
            os.rename(file_path, str(processed_path))
            logger.info(f"Documento processado com sucesso: {file_name}")
            
        except Exception as e:
            logger.error(f"Erro no processamento do documento: {e}")
            if os.path.exists(file_path):
                unprocessed_path = PathManager.get_unprocessed_path(file_name)
                os.rename(file_path, str(unprocessed_path))
                logger.info(f"Arquivo movido para não processados: {unprocessed_path}")
            raise

    async def process_video(self, file_path: str, file_name: str):
        """Processa arquivo de vídeo"""
        try:
            # Extrai texto do vídeo
            text = await self.video_processor.process(file_path)
            if not text.strip():
                raise ValueError("Texto extraído do vídeo vazio")
            
            # Prepara metadados
            metadata = {
                "file_name": file_name,
                "file_type": "video",
                "processed": True,
                "size": os.path.getsize(file_path),
                "duration": await self.video_processor.get_duration(file_path),
                "resolution": await self.video_processor.get_resolution(file_path)
            }
            
            # Salva no banco
            await self.db_manager.save_processed_content({
                "type": "video",
                "content": text,
                "metadata": metadata
            })
            
            # Move para processados
            processed_path = PathManager.get_processed_path(file_name)
            os.rename(file_path, str(processed_path))
            logger.info(f"Vídeo processado com sucesso: {file_name}")
            
        except Exception as e:
            logger.error(f"Erro processando vídeo: {e}")
            if os.path.exists(file_path):
                unprocessed_path = PathManager.get_unprocessed_path(file_name)
                os.rename(file_path, str(unprocessed_path))
                logger.info(f"Arquivo movido para não processados: {unprocessed_path}")
            raise

    async def get_documents(self, query: str = None):
        """Retorna documentos a partir da base de dados"""
        docs = await self.db_manager.get_documents(query=query, limit=100)
        return docs

    async def close(self):
        """Fecha conexões do MCP Server se necessário"""
        pass