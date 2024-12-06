import asyncio
import logging
import os
import warnings
import zipfile
import shutil
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from utils.queue_manager import QueueManager
from utils.db_manager import DatabaseManager
from mcp_server import DocumentMCPServer
from utils.statistics import ProcessingStats
from utils.path_manager import PathManager

warnings.filterwarnings("ignore")
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuração da API
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diretórios base
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "database" / "banco.db"
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost/")

UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH.parent.mkdir(exist_ok=True)

queue_manager = None
db_manager = None
mcp_server = None

class Mensagem(BaseModel):
    role: str
    content: str

class Pergunta(BaseModel):
    pergunta: str
    historico: List[Mensagem] = []

class ConsultaRequest(BaseModel):
    pergunta: str
    historico: List[Mensagem] = []

async def process_audio_task(message: dict):
    try:
        logger.info(f"[AUDIO_TASK] Iniciando processamento de áudio: {message}")
        for field in ['file_path', 'file_name', 'processed_dir', 'unprocessed_dir']:
            if field not in message:
                raise ValueError(f"[AUDIO_TASK] Campo obrigatório ausente: {field}")
        
        file_path = Path(message['file_path'])
        if not file_path.exists():
            logger.error(f"[AUDIO_TASK] Arquivo não encontrado: {file_path}")
            return

        logger.info(f"[AUDIO_TASK] Chamando mcp_server.process_audio para {file_path}")
        await mcp_server.process_audio(
            file_path=str(file_path),
            file_name=message['file_name'],
            processed_dir=message['processed_dir'],
            unprocessed_dir=message['unprocessed_dir']
        )
        logger.info(f"[AUDIO_TASK] Processamento de áudio concluído: {file_path}")
    except Exception as e:
        logger.error(f"[AUDIO_TASK] Erro processando áudio: {e}")

async def process_document_task(message: dict):
    try:
        logger.info(f"[DOC_TASK] Iniciando processamento de documento: {message}")
        for field in ['file_path', 'file_name', 'processed_dir', 'unprocessed_dir']:
            if field not in message:
                raise ValueError(f"[DOC_TASK] Campo obrigatório ausente: {field}")

        file_path = Path(message['file_path'])
        if not file_path.exists():
            logger.error(f"[DOC_TASK] Arquivo não encontrado: {file_path}")
            return

        logger.info(f"[DOC_TASK] Chamando mcp_server.process_document para {file_path}")
        await mcp_server.process_document(
            file_path=str(file_path),
            file_name=message['file_name'],
            processed_dir=message['processed_dir'],
            unprocessed_dir=message['unprocessed_dir']
        )
        logger.info(f"[DOC_TASK] Processamento de documento concluído: {file_path}")
    except Exception as e:
        logger.error(f"[DOC_TASK] Erro processando documento: {str(e)}")

async def process_image_task(message: dict):
    try:
        logger.info(f"[IMAGE_TASK] Iniciando processamento de imagem: {message}")
        for field in ['file_path', 'file_name', 'processed_dir', 'unprocessed_dir']:
            if field not in message:
                raise ValueError(f"[IMAGE_TASK] Campo obrigatório ausente: {field}")

        file_path = Path(message['file_path'])
        if not file_path.exists():
            logger.error(f"[IMAGE_TASK] Arquivo não encontrado: {file_path}")
            return

        logger.info(f"[IMAGE_TASK] Chamando mcp_server.process_image para {file_path}")
        success = await mcp_server.process_image(
            file_path=str(file_path),
            file_name=message['file_name'],
            processed_dir=message['processed_dir'],
            unprocessed_dir=message['unprocessed_dir']
        )

        if success:
            logger.info(f"[IMAGE_TASK] Imagem processada com sucesso: {file_path}")
        else:
            logger.error("[IMAGE_TASK] Falha no processamento da imagem")
    except Exception as e:
        logger.error(f"[IMAGE_TASK] Erro processando imagem: {e}")

async def process_video_task(message: dict):
    try:
        logger.info(f"[VIDEO_TASK] Iniciando processamento de vídeo: {message}")
        for field in ['file_path', 'file_name', 'processed_dir', 'unprocessed_dir']:
            if field not in message:
                raise ValueError(f"[VIDEO_TASK] Campo obrigatório ausente: {field}")
        
        file_path = Path(message['file_path'])
        if not file_path.exists():
            logger.error(f"[VIDEO_TASK] Arquivo não encontrado: {file_path}")
            return

        logger.info(f"[VIDEO_TASK] Chamando mcp_server.process_video para {file_path}")
        success = await mcp_server.process_video(
            file_path=str(file_path),
            file_name=message['file_name'],
            processed_dir=message['processed_dir'],
            unprocessed_dir=message['unprocessed_dir']
        )
        if success:
            logger.info(f"[VIDEO_TASK] Vídeo processado com sucesso: {file_path}")
        else:
            logger.error("[VIDEO_TASK] Falha no processamento do vídeo")
    except Exception as e:
        logger.error(f"[VIDEO_TASK] Erro processando vídeo: {e}")

async def start_queue_processors():
    """Inicia consumidores/consumidores para cada tipo de fila"""
    try:
        processors = {
            'audio': process_audio_task,
            'document': process_document_task,
            'image': process_image_task,
            'video': process_video_task
        }

        tasks = []
        for queue_type, processor in processors.items():
            queue_name = f"{queue_type}_processing"
            logger.info(f"[INIT] Iniciando processador para fila: {queue_name}")
            task = asyncio.create_task(
                queue_manager.process_queue(queue_name, processor)
            )
            tasks.append(task)
        
        app.state.processor_tasks = tasks
        logger.info("[INIT] Todos os processadores de fila iniciados")
    except Exception as e:
        logger.error(f"[INIT] Erro ao iniciar processadores: {e}")
        raise

async def init_database():
    """Inicializa o banco de dados"""
    try:
        db_manager = DatabaseManager(DB_PATH)
        await db_manager.initialize()
        return db_manager
    except Exception as e:
        logger.error(f"Erro inicializando banco de dados: {e}")
        raise

@app.on_event("startup")
async def startup_event():
    """Evento de inicialização da aplicação"""
    global db_manager, mcp_server, queue_manager
    
    try:
        logger.info("[STARTUP] Iniciando inicialização do banco de dados...")
        db_manager = await init_database()
        logger.info("Banco de dados inicializado")
        
        # Inicializa os diretórios
        PathManager.initialize()
        
        logger.info("[STARTUP] Iniciando MCP Server...")
        mcp_server = DocumentMCPServer(db_manager)
        await mcp_server.initialize()
        logger.info("MCP Server inicializado")
        
        logger.info("[STARTUP] Iniciando Queue Manager...")
        queue_manager = QueueManager(AMQP_URL, mcp_server)
        await queue_manager.initialize()
        
        # Configura os consumidores
        await queue_manager.setup_consumer('audio_processing', queue_manager.process_audio_message)
        await queue_manager.setup_consumer('document_processing', queue_manager.process_document_message)
        await queue_manager.setup_consumer('image_processing', queue_manager.process_image_message)
        await queue_manager.setup_consumer('video_processing', queue_manager.process_video_message)
        
        logger.info("Queue Manager inicializado")
        
    except Exception as e:
        logger.error(f"Erro na inicialização: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Finaliza conexões ao encerrar o servidor"""
    try:
        logger.info("[SHUTDOWN] Finalizando conexões...")
        processor_tasks = getattr(app.state, 'processor_tasks', [])
        for task in processor_tasks:
            if not task.done():
                task.cancel()

        if queue_manager:
            await queue_manager.close()
        if mcp_server:
            await mcp_server.close()
        if db_manager:
            await db_manager.close()

        logger.info("[SHUTDOWN] Conexões fechadas com sucesso")
    except Exception as e:
        logger.error(f"[SHUTDOWN] Erro ao finalizar conexões: {str(e)}")

@app.post("/upload")
async def upload_file(file: UploadFile):
    try:
        logger.info("[UPLOAD] Recebendo arquivo ZIP...")
        zip_path = UPLOAD_DIR / file.filename
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info("[UPLOAD] Iniciando processamento do ZIP...")
        result = await process_zip(zip_path=zip_path)

        # Verifica status das filas
        for queue_type in ['audio', 'document', 'image', 'video']:
            queue_name = f"{queue_type}_processing"
            await queue_manager.check_queue_status(queue_name)
            
        return result

    except Exception as e:
        logger.error(f"[UPLOAD] Erro no upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/consultar")
async def consultar(request: ConsultaRequest):
    try:
        # Primeiro, vamos listar todos os documentos
        docs = await db_manager.list_all_documents()
        
        if not docs:
            return {"resposta": "Nenhum documento relevante encontrado"}
            
        # Formata a resposta com conteúdo
        resposta = "Documentos processados:\n\n"
        for doc in docs:
            resposta += f"- {doc['file_name']} ({doc['file_type']})\n"
            resposta += f"  Conteúdo: {doc['content'][:200]}...\n\n"  # Mostra os primeiros 200 caracteres
            
        return {"resposta": resposta}
        
    except Exception as e:
        logger.error(f"Erro na consulta: {e}")
        return {"resposta": f"Erro ao processar consulta: {str(e)}"}

def get_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in ['.mp3', '.wav', '.ogg', '.opus', '.m4a']:
        return 'audio'
    elif ext in ['.pdf', '.docx', '.xlsx', '.xls', '.txt', '.vcf']:
        return 'document'
    elif ext in ['.jpg', '.jpeg', '.png']:
        return 'image'
    elif ext in ['.mp4', '.avi', '.mov']:
        return 'video'
    return None

async def process_zip(zip_path: Path):
    try:
        logger.info(f"[ZIP] Processando arquivo ZIP: {zip_path}")
        stats = ProcessingStats()
        with zipfile.ZipFile(zip_path) as zip_ref:
            all_files = zip_ref.namelist()
            valid_files = [f for f in all_files if get_file_type(f)]
            stats.total_files = len(valid_files)

            for arquivo_nome in all_files:
                try:
                    arquivo_path = UPLOAD_DIR / arquivo_nome
                    zip_ref.extract(arquivo_nome, UPLOAD_DIR)

                    file_type = get_file_type(arquivo_nome)
                    if file_type and arquivo_path.is_file():
                        task_data = {
                            'file_path': str(arquivo_path),
                            'file_name': arquivo_nome,
                            'processed_dir': str(PathManager.PROCESSED_DIR),
                            'unprocessed_dir': str(PathManager.UNPROCESSED_DIR)
                        }
                        logger.info(f"[ZIP] Enfileirando tarefa para {arquivo_nome} na fila {file_type}_processing")
                        await queue_manager.enqueue_task(file_type, task_data)
                        stats.processed_files += 1
                    else:
                        logger.warning(f"[ZIP] Arquivo não suportado ou não é arquivo regular: {arquivo_nome}")
                        if arquivo_path.is_file():
                            shutil.move(str(arquivo_path), str(PathManager.UNPROCESSED_DIR / arquivo_nome))
                        stats.failed_files += 1
                        stats.add_error(arquivo_nome, "Tipo de arquivo não suportado")

                except Exception as e:
                    logger.error(f"[ZIP] Erro processando arquivo {arquivo_nome}: {str(e)}")
                    extracted_file = UPLOAD_DIR / arquivo_nome
                    if extracted_file.exists():
                        shutil.move(str(extracted_file), str(PathManager.UNPROCESSED_DIR / arquivo_nome))
                    stats.failed_files += 1
                    stats.add_error(arquivo_nome, str(e))

        stats.save_log(zip_path.name)
        logger.info("[ZIP] Processamento do ZIP concluído. Estatísticas salvas.")
        
        return {
            "mensagem": "Processamento iniciado",
            "estatisticas": stats.to_dict()
        }

    except Exception as e:
        logger.error(f"[ZIP] Erro processando ZIP: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def check_status():
    try:
        logger.info("[STATUS] Verificando status...")
        processor_tasks = getattr(app.state, 'processor_tasks', [])
        active_processors = [task for task in processor_tasks if not task.done() and not task.cancelled()]

        return {
            "status": "running" if active_processors else "stopped",
            "active_processors": len(active_processors),
            "total_processors": len(processor_tasks)
        }
    except Exception as e:
        logger.error(f"[STATUS] Erro ao verificar status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/purge-queues")
async def purge_queues():
    try:
        logger.info("[PURGE] Purga de filas solicitada...")
        await queue_manager.purge_queues()
        return {"message": "Filas limpas com sucesso"}
    except Exception as e:
        logger.error(f"[PURGE] Erro ao limpar filas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-file")
async def process_file(file: UploadFile):
    try:
        logger.info("[PROCESS_FILE] Recebendo arquivo único para processamento...")
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        file_type = get_file_type(file.filename)
        if not file_type:
            logger.warning(f"[PROCESS_FILE] Tipo de arquivo não suportado: {file.filename}")
            unprocessed_path = PathManager.get_unprocessed_path(file.filename)
            shutil.move(str(file_path), str(unprocessed_path))
            return {"message": f"Tipo de arquivo não suportado: {file.filename}"}

        message = {
            "file_path": str(file_path),
            "file_name": file.filename,
            "processed_dir": str(PathManager.PROCESSED_DIR),
            "unprocessed_dir": str(PathManager.UNPROCESSED_DIR)
        }

        logger.info(f"[PROCESS_FILE] Enfileirando tarefa para {file.filename} na fila {file_type}_processing")
        await queue_manager.enqueue_task(file_type, message)

        return {"message": f"Arquivo {file.filename} enviado para processamento"}

    except Exception as e:
        logger.error(f"[PROCESS_FILE] Erro processando arquivo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def init_queue_processors():
    """Inicializa os processadores de fila"""
    try:
        queue_manager = QueueManager()
        await queue_manager.initialize()
        
        # Configura os callbacks para cada tipo de fila
        await queue_manager.setup_consumer('audio_processing', queue_manager.process_audio_message)
        await queue_manager.setup_consumer('image_processing', queue_manager.process_image_message)
        # ... outros consumidores ...
        
        logger.info("Todos os processadores de fila iniciados")
        
    except Exception as e:
        logger.error(f"Erro ao inicializar processadores: {e}")
        raise

if __name__ == "__main__":
    import uvicorn
    logger.info("[MAIN] Iniciando servidor na porta 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)