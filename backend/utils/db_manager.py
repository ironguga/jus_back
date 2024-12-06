import os
import json
import asyncio
import aiosqlite
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from asyncio import Lock

logger = logging.getLogger(__name__)

# Definindo o caminho do banco de dados
BASE_DIR = Path(__file__).parent.parent  # volta um nível para a pasta backend
DB_PATH = BASE_DIR / "database" / "banco.db"

# Cria o diretório do banco se não existir
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
        """
        Inicializa o banco de dados, cria as tabelas e configura o pool de conexões.
        """
        # Garante diretório do banco
        os.makedirs(self.db_path.parent, exist_ok=True)

        # Cria uma conexão inicial para criar tabelas, etc.
        self.conn = await aiosqlite.connect(self.db_path)
        self.cursor = await self.conn.cursor()

        # Cria tabelas se não existirem
        await self.create_tables()

        # Configura o pool
        await self._setup_connection_pool()

        logger.info("Banco de dados inicializado com sucesso")

    async def create_tables(self):
        """
        Cria as tabelas necessárias.
        """
        try:
            async with self.get_connection() as conn:
                # Cria tabela documentos
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS documentos (
                        id TEXT PRIMARY KEY,
                        nome_arquivo TEXT NOT NULL,
                        conteudo TEXT,
                        metadados TEXT,
                        tipo_documento TEXT,
                        tamanho INTEGER,
                        hash TEXT UNIQUE,
                        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Cria tabela processed_content
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS processed_content (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                await conn.commit()
                logger.info("Tabelas criadas/verificadas com sucesso")
        except Exception as e:
            logger.error(f"Erro criando tabelas: {e}")
            raise

    async def _setup_connection_pool(self):
        """
        Configura o pool de conexões a partir do número de conexões especificado.
        """
        async with self._pool_lock:
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(self.db_path)
                # Ajustes de performance (opcionais)
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA cache_size=-64000")
                await conn.execute("PRAGMA temp_store=MEMORY")
                await conn.execute("PRAGMA mmap_size=268435456")

                self._connection_pool.append(conn)

    @asynccontextmanager
    async def get_connection(self):
        """
        Retorna uma conexão do pool para uso dentro de um contexto assíncrono.
        Ao sair do contexto, a conexão é devolvida ao pool.
        """
        async with self._pool_lock:
            if self._connection_pool:
                conn = self._connection_pool.pop()
            else:
                # Se pool estiver vazio, cria nova conexão
                conn = await aiosqlite.connect(self.db_path)

        try:
            yield conn
        finally:
            await self.release_connection(conn)

    async def release_connection(self, conn: aiosqlite.Connection):
        """
        Devolve a conexão ao pool, ou fecha se o pool estiver cheio.
        """
        async with self._pool_lock:
            if len(self._connection_pool) < self.pool_size:
                self._connection_pool.append(conn)
            else:
                await conn.close()

    async def add_document(self, id: str, nome_arquivo: str, conteudo: str, 
                          metadados: str, tipo_documento: str, tamanho: int, hash: str):
        """
        Insere um novo documento no banco de dados.
        """
        query = """
            INSERT INTO documentos (
                id, nome_arquivo, conteudo, metadados, 
                tipo_documento, tamanho, hash, data_criacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """
        async with self.get_connection() as conn:
            await conn.execute(query, (id, nome_arquivo, conteudo, metadados, tipo_documento, tamanho, hash))
            await conn.commit()

    async def get_documents(self, query: str = None, limit: int = 100):
        """
        Retorna documentos filtrados por texto no conteúdo, se query for fornecida.
        Limita por padrão a 100 resultados.
        """
        async with self.get_connection() as conn:
            cursor = await conn.cursor()
            if query:
                await cursor.execute("""
                    SELECT id, nome_arquivo, conteudo, metadados, tipo_documento, tamanho, hash, data_criacao
                    FROM documentos
                    WHERE conteudo LIKE ?
                    ORDER BY data_criacao DESC
                    LIMIT ?
                """, (f"%{query}%", limit))
            else:
                await cursor.execute("""
                    SELECT id, nome_arquivo, conteudo, metadados, tipo_documento, tamanho, hash, data_criacao
                    FROM documentos
                    ORDER BY data_criacao DESC
                    LIMIT ?
                """, (limit,))

            rows = await cursor.fetchall()
            docs = []
            for row in rows:
                doc = {
                    "id": row[0],
                    "file_name": row[1],
                    "content": row[2],
                    "metadados": json.loads(row[3]) if row[3] else {},
                    "tipo_documento": row[4],
                    "tamanho": row[5],
                    "hash": row[6],
                    "data_criacao": row[7]
                }
                docs.append(doc)
            return docs

    async def close(self):
        """
        Fecha todas as conexões, incluindo o pool.
        """
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

    async def save_audio_result(self, file_name: str, transcription: str, file_path: str):
        """Salva resultado da transcrição de áudio no banco."""
        try:
            logger.info(f"Salvando transcrição para arquivo: {file_name}")
            async with self._get_connection() as conn:
                query = """
                    INSERT INTO documents (file_name, content, file_path) 
                    VALUES (?, ?, ?)
                """
                await conn.execute(query, (file_name, transcription, file_path))
                await conn.commit()
                logger.info(f"Transcrição salva com sucesso: {file_name}")
        except Exception as e:
            logger.error(f"Erro ao salvar transcrição para {file_name}: {e}", exc_info=True)
            raise

    async def save_processed_content(self, content_data: dict):
        """Salva o conteúdo processado no banco de dados"""
        try:
            logger.info(f"Tentando salvar conteúdo no banco: {content_data['metadata']['file_name']}")
            async with self.get_connection() as conn:
                # Adiciona logs para debug
                logger.debug(f"Dados recebidos: {content_data}")
                
                # Verifica se já existe
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
                
                # Insere novo registro
                await conn.execute('''
                    INSERT INTO processed_content 
                    (file_name, file_type, content_type, content, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    content_data['metadata']['file_name'],
                    content_data['metadata']['file_type'],
                    content_data['type'],
                    content_data['content'],
                    json.dumps(content_data['metadata'])
                ))
                await conn.commit()
                
                # Verifica se foi salvo
                cursor = await conn.execute('SELECT COUNT(*) FROM processed_content')
                count = await cursor.fetchone()
                logger.info(f"Total de documentos após inserção: {count[0]}")
                
                logger.info(f"Conteúdo salvo com sucesso: {content_data['metadata']['file_name']}")
                
        except Exception as e:
            logger.error(f"Erro ao salvar conteúdo no banco: {str(e)}")
            logger.error(f"Dados que tentamos salvar: {content_data}")
            raise

    async def list_all_documents(self):
        """Lista todos os documentos processados"""
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute('''
                    SELECT file_name, file_type, content_type, content 
                    FROM processed_content 
                    ORDER BY created_at DESC
                ''')
                rows = await cursor.fetchall()
                
                if not rows:
                    return []
                    
                documents = []
                for row in rows:
                    documents.append({
                        "file_name": row[0],
                        "file_type": row[1],
                        "content_type": row[2],
                        "content": row[3]
                    })
                    
                return documents
                
        except Exception as e:
            self.logger.error(f"Erro listando documentos: {e}")
            return []

async def init_database():
    """Inicializa o banco de dados"""
    try:
        db_manager = DatabaseManager()  # Agora usa o DB_PATH definido no módulo
        await db_manager.initialize()
        return db_manager
    except Exception as e:
        logger.error(f"Erro inicializando banco de dados: {e}")
        raise