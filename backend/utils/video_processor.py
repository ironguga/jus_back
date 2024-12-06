import logging
import cv2
from pathlib import Path

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialized = False

    async def initialize(self):
        """Inicializa o processador de vídeos"""
        if self._initialized:
            return
            
        try:
            self.logger.info("Inicializando VideoProcessor...")
            self._initialized = True
            self.logger.info("VideoProcessor inicializado com sucesso")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar VideoProcessor: {e}")
            raise

    async def process(self, file_path: str) -> str:
        """Processa um vídeo e extrai informações relevantes"""
        try:
            if not self._initialized:
                await self.initialize()

            # Por enquanto retorna apenas metadados como texto
            duration = await self.get_duration(file_path)
            resolution = await self.get_resolution(file_path)
            
            text = f"Vídeo processado. Duração: {duration}s, Resolução: {resolution['width']}x{resolution['height']}"
            return text
            
        except Exception as e:
            self.logger.error(f"Erro processando vídeo {file_path}: {e}")
            raise

    async def get_duration(self, file_path: str) -> float:
        """Retorna a duração do vídeo em segundos"""
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return 0.0
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count/fps
            
            cap.release()
            return round(duration, 2)
            
        except Exception as e:
            self.logger.error(f"Erro obtendo duração do vídeo {file_path}: {e}")
            return 0.0

    async def get_resolution(self, file_path: str) -> dict:
        """Retorna as dimensões do vídeo"""
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return {"width": 0, "height": 0}
            
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            cap.release()
            return {"width": width, "height": height}
            
        except Exception as e:
            self.logger.error(f"Erro obtendo resolução do vídeo {file_path}: {e}")
            return {"width": 0, "height": 0}