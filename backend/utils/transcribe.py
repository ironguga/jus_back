import whisper
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self):
        self.model = whisper.load_model("base")
        logger.info("Modelo Whisper carregado")
        
    async def process(self, file_path: str) -> str:
        try:
            result = self.model.transcribe(file_path)
            return result["text"]
        except Exception as e:
            logger.error(f"Erro transcrevendo áudio: {e}")
            raise

    async def transcribe_audio(self, file_path: str) -> str:
        """Alias para process"""
        return await self.process(file_path)