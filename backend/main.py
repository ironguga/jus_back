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
from utils.statistics import ProcessingStats
from utils.path_manager import PathManager
from utils.mcp_server import DocumentMCPServer
from utils.summarizer import Summarizer
from utils.azure_integration import search_in_azure, index_in_azure_search
from utils.vector_search import VectorSearcher  # Opcional, se tiver embeddings

warnings.filterwarnings("ignore")
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost/")
UPLOAD_DIR.mkdir(exist_ok=True)

queue_manager = None
mcp_server = None
summarizer = Summarizer()  # Instância global do sumarizador
vector_searcher = VectorSearcher()  # Instância global do vector search (opcional)


class Mensagem(BaseModel):
    role: str
    content: str


class ConsultaRequest(BaseModel):
    pergunta: str
    historico: List[Mensagem] = []


@app.on_event("startup")
async def startup_event():
    global mcp_server, queue_manager
    
    try:
        logger.info("[STARTUP] Iniciando inicialização...")
        
        PathManager.initialize()

        logger.info("[STARTUP] Iniciando MCP Server...")
        if not mcp_server:
            mcp_server_inst = DocumentMCPServer()
            await mcp_server_inst.initialize()
            mcp_server = mcp_server_inst

        from utils.queue_manager import QueueManager
        queue_manager = QueueManager(AMQP_URL, mcp_server)
        await queue_manager.initialize()

        # Configura consumidores
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
    try:
        logger.info("[SHUTDOWN] Finalizando conexões...")
        if queue_manager:
            await queue_manager.close()
        if mcp_server:
            await mcp_server.close()
        logger.info("[SHUTDOWN] Conexões fechadas com sucesso")
    except Exception as e:
        logger.error(f"[SHUTDOWN] Erro ao finalizar conexões: {str(e)}")


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
        logger.info("[ZIP] Processando arquivo ZIP: %s", zip_path)
        stats = ProcessingStats()
        with zipfile.ZipFile(zip_path) as zip_ref:
            all_files = zip_ref.namelist()
            valid_files = [f for f in all_files if get_file_type(f)]
            stats.total_files = len(valid_files)

            for arquivo_nome in all_files:
                arquivo_path = UPLOAD_DIR / arquivo_nome
                try:
                    zip_ref.extract(arquivo_nome, UPLOAD_DIR)
                    file_type = get_file_type(arquivo_nome)
                    if file_type and arquivo_path.is_file():
                        content_data = await process_single_file(arquivo_path, arquivo_nome, file_type)
                        if content_data:
                            await index_in_azure_search(content_data)
                            processed_path = PathManager.get_processed_path(arquivo_nome)
                            os.rename(arquivo_path, processed_path)
                            stats.saved_to_db += 1
                        stats.processed_files += 1
                    else:
                        logger.warning("[ZIP] Arquivo não suportado: %s", arquivo_nome)
                        if arquivo_path.is_file():
                            shutil.move(str(arquivo_path), str(PathManager.get_unprocessed_path(arquivo_nome)))
                        stats.add_error(arquivo_nome, "Tipo de arquivo não suportado")
                except Exception as e:
                    logger.error("[ZIP] Erro processando arquivo %s: %s", arquivo_nome, str(e))
                    if arquivo_path.exists():
                        shutil.move(str(arquivo_path), str(PathManager.get_unprocessed_path(arquivo_nome)))
                    stats.add_error(arquivo_nome, str(e))

        stats.save_log(zip_path.name)
        logger.info("[ZIP] Processamento do ZIP concluído. Estatísticas salvas.")
        
        await mcp_server.initialize()

        return {
            "mensagem": "Processamento iniciado",
            "estatisticas": stats.to_dict()
        }

    except Exception as e:
        logger.error("[ZIP] Erro processando ZIP: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def process_single_file(file_path: Path, file_name: str, file_type: str):
    if file_type == 'audio':
        transcription = await mcp_server.audio_processor.transcribe_audio(str(file_path))
        summary = summarizer.summarize(transcription, max_length=100)
        return {
            "type": "audio",
            "content": transcription,
            "metadata": {
                "file_name": file_name,
                "file_type": "audio",
                "summary": summary
            }
        }
    elif file_type == 'image':
        text = await mcp_server.image_processor.process(str(file_path))
        summary = summarizer.summarize(text, max_length=100)
        return {
            "type": "image",
            "content": text,
            "metadata": {
                "file_name": file_name,
                "file_type": "image",
                "summary": summary
            }
        }
    elif file_type == 'document':
        text = await mcp_server.document_processor.process(str(file_path))
        summary = summarizer.summarize(text, max_length=100)
        return {
            "type": "document",
            "content": text,
            "metadata": {
                "file_name": file_name,
                "file_type": "document",
                "summary": summary
            }
        }
    elif file_type == 'video':
        text = await mcp_server.video_processor.process(str(file_path))
        summary = summarizer.summarize(text, max_length=100)
        return {
            "type": "video",
            "content": text,
            "metadata": {
                "file_name": file_name,
                "file_type": "video",
                "summary": summary
            }
        }
    else:
        logger.warning("Tipo de arquivo não suportado.")
        return None


@app.post("/upload")
async def upload_file(file: UploadFile):
    try:
        logger.info("[UPLOAD] Recebendo arquivo ZIP...")
        zip_path = UPLOAD_DIR / file.filename
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info("[UPLOAD] Iniciando processamento do ZIP...")
        result = await process_zip(zip_path=zip_path)
        return result

    except Exception as e:
        logger.error("[UPLOAD] Erro no upload: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/consultar")
async def consultar(request: ConsultaRequest):
    try:
        # Convertemos o historico (lista de Mensagem) em lista de dicts
        historico_limitado = request.historico[-2:] if len(request.historico) > 2 else request.historico
        historico_dicts = [{"role": m.role, "content": m.content} for m in historico_limitado]

        pergunta = request.pergunta.lower()

        # Definindo paginação padrão
        skip = 0
        top = 50

        if "quantos documentos" in pergunta or "quantidade de documentos" in pergunta:
            docs = await search_in_azure("*", skip=skip, top=1)
            resposta = f"Não tenho informação da contagem total. Retornei {len(docs)} documentos nesta página."
            return {"resposta": resposta}

        elif "overview" in pergunta or "resumo de todos" in pergunta or "o que todos os documentos" in pergunta:
            docs = await search_in_azure("*", skip=0, top=50)
            all_summaries = []
            for d in docs:
                short_summary = summarizer.summarize(d['content'], max_length=50)
                all_summaries.append(f"Documento {d['id']} ({d['file_name']}): {short_summary}")
            combined_text = "\n".join(all_summaries)
            final_overview = summarizer.summarize(combined_text, max_length=200)
            return {"resposta": final_overview}

        elif "sobre" in pergunta or "assunto" in pergunta or "tema" in pergunta:
            palavras = pergunta.split()
            keyword = palavras[-1]

            doc_ids_vector = vector_searcher.search(keyword, top=10)
            if not doc_ids_vector:
                docs = await search_in_azure(keyword, skip=0, top=10)
            else:
                docs = await search_in_azure(keyword, skip=0, top=10)

            contexto = ""
            for d in docs:
                trecho = d['content'][:200]
                contexto += f"[Doc {d['id']} - {d['file_name']}: {trecho}]\n"
            resposta = await mcp_server.process_query(request.pergunta, historico_dicts, contexto=contexto)
            return {"resposta": resposta}

        else:
            vdocs = vector_searcher.search(request.pergunta, top=5)
            if not vdocs:
                docs = await search_in_azure(request.pergunta, skip=0, top=5)
            else:
                docs = await search_in_azure(request.pergunta, skip=0, top=5)

            contexto = ""
            for d in docs:
                trecho = d['content'][:300]
                contexto += f"[Doc {d['id']} ({d['file_name']}): {trecho}]\n"

            resposta = await mcp_server.process_query(request.pergunta, historico_dicts, contexto=contexto)
            return {"resposta": resposta}

    except Exception as e:
        logger.error("Erro na consulta: %s", str(e))
        return {"resposta": f"Erro ao processar consulta: {str(e)}"}


@app.get("/status")
async def check_status():
    return {"status": "running"}


@app.post("/purge-queues")
async def purge_queues():
    await queue_manager.purge_queues()
    return {"message": "Filas limpas"}


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
            logger.warning("[PROCESS_FILE] Tipo de arquivo não suportado: %s", file.filename)
            unprocessed_path = PathManager.get_unprocessed_path(file.filename)
            shutil.move(str(file_path), str(unprocessed_path))
            return {"message": f"Tipo de arquivo não suportado: {file.filename}"}

        content_data = await process_single_file(file_path, file.filename, file_type)
        if content_data:
            await index_in_azure_search(content_data)
            processed_path = PathManager.get_processed_path(file.filename)
            os.rename(file_path, processed_path)
            await mcp_server.initialize()

        return {"message": f"Arquivo {file.filename} processado e salvo"}

    except Exception as e:
        logger.error("[PROCESS_FILE] Erro processando arquivo: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    logger.info("[MAIN] Iniciando servidor na porta 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)