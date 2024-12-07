# utils/db_manager.py
import os
import json
import asyncio
import aiosqlite
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from asyncio import Lock
import datetime

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "database" / "banco.db"
DB_PATH.parent.mkdir(exist_ok=True)

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.pool_size = 5
        self._connection_pool = []
        self._pool_lock = Lock()
        
    async def initialize(self):
        os.makedirs(self.db_path.parent, exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        self.cursor = await self.conn.cursor()
        await self.create_tables()
        await self._setup_connection_pool()
        logger.info("Banco de dados inicializado com sucesso")

    async def create_tables(self):
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS processed_content (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata TEXT,
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await conn.commit()
                logger.info("Tabelas criadas/verificadas com sucesso")
        except Exception as e:
            logger.error(f"Erro criando tabelas: {e}")
            raise

    async def _setup_connection_pool(self):
        async with self._pool_lock:
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(self.db_path)
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA cache_size=-64000")
                await conn.execute("PRAGMA temp_store=MEMORY")
                await conn.execute("PRAGMA mmap_size=268435456")
                self._connection_pool.append(conn)

    @asynccontextmanager
    async def get_connection(self):
        async with self._pool_lock:
            if self._connection_pool:
                conn = self._connection_pool.pop()
            else:
                conn = await aiosqlite.connect(self.db_path)
        try:
            yield conn
        finally:
            await self.release_connection(conn)

    async def release_connection(self, conn: aiosqlite.Connection):
        async with self._pool_lock:
            if len(self._connection_pool) < self.pool_size:
                self._connection_pool.append(conn)
            else:
                await conn.close()

    async def save_processed_content(self, content_data: dict):
        try:
            logger.info(f"Tentando salvar conteúdo no banco: {content_data['metadata']['file_name']}")
            async with self.get_connection() as conn:
                cursor = await conn.execute('''
                    SELECT id FROM processed_content 
                    WHERE file_name = ? AND file_type = ?
                ''', (
                    content_data['metadata']['file_name'],
                    content_data['metadata']['file_type']
                ))
                existing = await cursor.fetchone()
                if existing:
                    logger.info(f"Documento já existe no banco: {content_data['metadata']['file_name']}")
                    return
                
                await conn.execute('''
                    INSERT INTO processed_content 
                    (file_name, file_type, content_type, content, metadata, summary)
                    VALUES (?, ?, ?, ?, ?, '')
                ''', (
                    content_data['metadata']['file_name'],
                    content_data['metadata']['file_type'],
                    content_data['type'],
                    content_data['content'],
                    json.dumps(content_data['metadata'])
                ))
                await conn.commit()
                cursor = await conn.execute('SELECT COUNT(*) FROM processed_content')
                count = await cursor.fetchone()
                logger.info(f"Total de documentos após inserção: {count[0]}")
                logger.info(f"Conteúdo salvo com sucesso: {content_data['metadata']['file_name']}")
        except Exception as e:
            logger.error(f"Erro ao salvar conteúdo no banco: {str(e)}")
            logger.error(f"Dados que tentamos salvar: {content_data}")
            raise

    async def list_all_processed_documents(self):
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute('''
                    SELECT id, file_name, file_type, content_type, content, metadata, summary
                    FROM processed_content 
                    ORDER BY created_at DESC
                ''')
                rows = await cursor.fetchall()
                if not rows:
                    return []
                documents = []
                for row in rows:
                    documents.append({
                        "id": row[0],
                        "file_name": row[1],
                        "file_type": row[2],
                        "content_type": row[3],
                        "content": row[4],
                        "metadata": json.loads(row[5]) if row[5] else {},
                        "summary": row[6] if row[6] else ""
                    })
                return documents
        except Exception as e:
            logger.error(f"Erro listando documentos: {e}")
            return []

    async def update_summary(self, doc_id: int, summary: str):
        try:
            async with self.get_connection() as conn:
                await conn.execute('UPDATE processed_content SET summary = ? WHERE id = ?', (summary, doc_id))
                await conn.commit()
        except Exception as e:
            logger.error(f"Erro ao atualizar sumário: {e}")

    async def close(self):
        async with self._pool_lock:
            for conn in self._connection_pool:
                try:
                    await conn.close()
                except Exception as e:
                    logger.error(f"Erro ao fechar conexão: {e}")
            self._connection_pool.clear()

        if self.cursor:
            await self.cursor.close()
        if self.conn:
            await self.conn.close()