import fitz  # PyMuPDF
import pandas as pd
import pytesseract
from PIL import Image
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self.supported_extensions = {
            'txt': self._process_text,
            'pdf': self._process_pdf,
            'xlsx': self._process_excel,
            'xls': self._process_excel,
            'vcf': self._process_text
        }

    async def initialize(self):
        """Inicializa o processador de documentos"""
        if self._initialized:
            self.logger.debug("DocumentProcessor já inicializado")
            return
            
        try:
            self.logger.info("Inicializando DocumentProcessor...")
            # Aqui podemos adicionar qualquer inicialização necessária
            self._initialized = True
            self.logger.info("DocumentProcessor inicializado com sucesso")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar DocumentProcessor: {str(e)}")
            raise

    async def process(self, file_path: str) -> str:
        """Processa o documento e retorna o texto extraído"""
        if not self._initialized:
            await self.initialize()
            
        try:
            path = Path(file_path)
            extension = path.suffix.lower()[1:]
            
            if extension in self.supported_extensions:
                processor = self.supported_extensions[extension]
                return await processor(path)
            else:
                self.logger.warning(f"Extensão não suportada: {extension}")
                return f"Formato não suportado: {extension}"
                
        except Exception as e:
            self.logger.error(f"Erro processando documento: {e}")
            raise

    async def _process_text(self, file_path: Path) -> str:
        """Processa arquivos de texto"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"Erro processando arquivo de texto: {e}")
            raise

    async def _process_pdf(self, file_path: Path) -> str:
        """Processa arquivos PDF"""
        try:
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            return text
        except Exception as e:
            self.logger.error(f"Erro processando PDF: {e}")
            raise

    async def _process_excel(self, file_path: Path) -> str:
        """Processa arquivos Excel"""
        try:
            df = pd.read_excel(file_path)
            return df.to_string()
        except Exception as e:
            self.logger.error(f"Erro processando Excel: {e}")
            raise