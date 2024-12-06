import logging
from pathlib import Path
from typing import List
from .document_processor import DocumentProcessor
from .audio_processor import AudioProcessor
from .db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class ProcessingManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.document_processor = DocumentProcessor()
        self.audio_processor = AudioProcessor()
        
    async def process_files(self, file_paths: List[Path]):
        """Processa uma lista de arquivos"""
        total_processed = 0
        total_failed = 0
        
        for file_path in file_paths:
            try:
                logger.info(f"Iniciando processamento do arquivo: {file_path}")
                result = await self._process_single_file(file_path)
                
                if result and 'error' not in result:
                    logger.info(f"Arquivo processado, salvando no banco: {file_path}")
                    await self.db_manager.save_processed_content(result)
                    total_processed += 1
                    logger.info(f"Arquivo processado e salvo com sucesso: {file_path}")
                else:
                    logger.warning(f"Falha ao processar arquivo: {file_path}")
                    total_failed += 1
                    
            except Exception as e:
                logger.error(f"Erro ao processar {file_path}: {str(e)}")
                total_failed += 1
                
        logger.info(f"Processamento concluído. Processados: {total_processed}, Falhas: {total_failed}")
        return total_processed, total_failed

    async def _process_single_file(self, file_path: Path):
        """Processa um único arquivo baseado em sua extensão"""
        extension = file_path.suffix.lower()[1:]
        
        # Arquivos de mídia (áudio/vídeo)
        if extension in self.audio_processor.supported_audio_extensions.union(
                self.audio_processor.supported_video_extensions):
            return await self.audio_processor.process_media(file_path)
            
        # Documentos e imagens
        elif extension in self.document_processor.supported_extensions:
            return await self.document_processor.process_document(file_path)
            
        else:
            logger.warning(f"Extensão não suportada: {extension}")
            return {"error": "Formato não suportado"} 