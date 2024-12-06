import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class PathManager:
    BASE_DIR = Path("/Users/gustavoferro/Apps/just_back/backend/uploads")
    PROCESSED_DIR = BASE_DIR / "processed"
    UNPROCESSED_DIR = BASE_DIR / "unprocessed"

    @classmethod
    def initialize(cls):
        """Inicializa as pastas necessárias"""
        try:
            # Cria as pastas se não existirem
            cls.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            cls.UNPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Diretórios inicializados: {cls.PROCESSED_DIR}, {cls.UNPROCESSED_DIR}")
        except Exception as e:
            logger.error(f"Erro ao criar diretórios: {e}")
            raise

    @classmethod
    def get_processed_path(cls, filename: str) -> Path:
        """Retorna o caminho completo para um arquivo processado"""
        return cls.PROCESSED_DIR / filename

    @classmethod
    def get_unprocessed_path(cls, filename: str) -> Path:
        """Retorna o caminho completo para um arquivo não processado"""
        return cls.UNPROCESSED_DIR / filename 