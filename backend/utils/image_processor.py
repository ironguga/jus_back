import logging
from PIL import Image
import pytesseract
from pathlib import Path

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialized = False

    async def initialize(self):
        """Inicializa o processador de imagens"""
        if self._initialized:
            return
            
        try:
            self.logger.info("Inicializando ImageProcessor...")
            # Aqui podemos adicionar configurações do tesseract se necessário
            self._initialized = True
            self.logger.info("ImageProcessor inicializado com sucesso")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar ImageProcessor: {e}")
            raise

    async def process(self, file_path: str) -> str:
        """Processa uma imagem e extrai o texto usando OCR"""
        try:
            if not self._initialized:
                await self.initialize()

            image = Image.open(file_path)
            
            # Converte para RGB se necessário (para imagens PNG com transparência)
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            
            # Configura o OCR para português
            text = pytesseract.image_to_string(image, lang='por')
            
            # Limpa o texto
            text = text.strip()
            
            if not text:
                self.logger.warning(f"Nenhum texto encontrado na imagem: {file_path}")
            else:
                self.logger.info(f"Texto extraído com sucesso da imagem: {file_path}")
                
            return text
            
        except Exception as e:
            self.logger.error(f"Erro processando imagem {file_path}: {e}")
            raise

    async def get_dimensions(self, file_path: str) -> dict:
        """Retorna as dimensões da imagem"""
        try:
            with Image.open(file_path) as img:
                width, height = img.size
                return {
                    "width": width,
                    "height": height,
                    "aspect_ratio": round(width/height, 2)
                }
        except Exception as e:
            self.logger.error(f"Erro obtendo dimensões da imagem {file_path}: {e}")
            return {"width": 0, "height": 0, "aspect_ratio": 0}