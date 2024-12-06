import logging
from dataclasses import dataclass, field
from typing import List, Dict
from pathlib import Path
import json
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ProcessingStats:
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    saved_to_db: int = 0
    errors: List[Dict] = field(default_factory=list)
    
    def add_error(self, file_name: str, error: str):
        """Adiciona erro às estatísticas."""
        error_entry = {
            "file": file_name,
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        }
        logger.error(f"Erro processando arquivo: {file_name} - {error}")
        self.errors.append(error_entry)
        self.failed_files += 1
    
    def to_dict(self):
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "saved_to_db": self.saved_to_db,
            "success_rate": f"{(self.processed_files/self.total_files)*100:.2f}%" if self.total_files > 0 else "0%",
            "errors": self.errors
        }
    
    def save_log(self, zip_name: str):
        """Salva log de processamento."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"processing_{timestamp}_{zip_name}.json"
        
        stats = self.to_dict()
        logger.info(f"Estatísticas finais: {stats['processed_files']}/{stats['total_files']} processados ({stats['success_rate']})")
        
        with open(log_file, "w") as f:
            json.dump(stats, f, indent=2)
        logger.info(f"Log de processamento salvo em: {log_file}") 