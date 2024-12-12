import logging
import asyncio

from utils.transcribe import AudioProcessor
from utils.image_processor import ImageProcessor
from utils.document_processor import DocumentProcessor
from utils.video_processor import VideoProcessor
from utils.path_manager import PathManager

logger = logging.getLogger(__name__)

class DocumentMCPServer:
    def __init__(self):
        self.audio_processor = AudioProcessor()
        self.image_processor = ImageProcessor()
        self.document_processor = DocumentProcessor()
        self.video_processor = VideoProcessor()
        self._initialized = False

    async def initialize(self):
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
        pass

    async def process_audio(self, file_path: str, file_name: str):
        text = await self.audio_processor.process(file_path)
        return text

    async def process_image(self, file_path: str, file_name: str):
        text = await self.image_processor.process(file_path)
        return text

    async def process_document(self, file_path: str, file_name: str):
        text = await self.document_processor.process(file_path)
        return text

    async def process_video(self, file_path: str, file_name: str):
        text = await self.video_processor.process(file_path)
        return text

    async def process_query(self, query: str, historico, contexto: str = ""):
        if not self._initialized:
            return "O servidor não foi inicializado corretamente."
        # Não precisamos mais usar aqui. A lógica está toda em main.py.
        return "Função não utilizada no momento."