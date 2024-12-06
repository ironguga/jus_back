from pathlib import Path
from utils.db_manager import DatabaseManager
from utils.processing_manager import ProcessingManager
import asyncio
import logging
import sqlite3

logger = logging.getLogger(__name__)

async def init_database():
    """Inicializa e otimiza o banco de dados"""
    try:
        db_path = Path(__file__).parent / "database" / "banco.db"
        db_path.parent.mkdir(exist_ok=True)
        
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize()
        
        # Criar o processing manager
        processing_manager = ProcessingManager(db_manager)
        
        logger.info("Sistema inicializado com sucesso")
        return db_manager, processing_manager
        
    except Exception as e:
        logger.error(f"Erro ao inicializar sistema: {str(e)}")
        raise

def init_db():
    """Inicializa o banco de dados com a estrutura necessária"""
    try:
        db_path = Path(__file__).parent / "database" / "banco.db"
        db_path.parent.mkdir(exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabela para conteúdo processado
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            content_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Índices para melhorar performance de busca
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_content ON processed_content(content);
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_file_type ON processed_content(file_type);
        ''')

        conn.commit()
        logger.info("Banco de dados inicializado com sucesso")
        
    except Exception as e:
        logger.error(f"Erro inicializando banco de dados: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_database())
    init_db() 