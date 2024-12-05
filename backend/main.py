from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import sqlite3
import zipfile
import shutil
import os
from anthropic import Anthropic
from utils.ocr import extrair_texto_imagem
from utils.pdf_reader import extrair_texto_pdf, extrair_texto_docx, extrair_texto_excel, extrair_texto_vcf, extrair_texto_video
from utils.transcribe import transcrever_audio
from dotenv import load_dotenv
import warnings
from typing import List
from mcp_server import DocumentMCPServer
import logging

# Suprimir avisos
warnings.filterwarnings("ignore")

# Carregar variáveis de ambiente
load_dotenv()

# Configurar cliente Anthropic com a chave de API
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY não encontrada nas variáveis de ambiente")

# Configuração da API
app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração de diretórios
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "database" / "banco.db"

# Criar diretórios necessários
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH.parent.mkdir(exist_ok=True)

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def inicializar_banco():
    """Inicializa o banco de dados"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY,
            nome_arquivo TEXT,
            conteudo TEXT
        )
    """)
    conn.commit()
    conn.close()

def processar_arquivo(caminho_arquivo: Path) -> str:
    """Processa um arquivo e retorna o texto extraído"""
    sufixo = caminho_arquivo.suffix.lower()
    
    try:
        if sufixo in ['.jpg', '.jpeg', '.png']:
            return extrair_texto_imagem(caminho_arquivo)
        elif sufixo == '.pdf':
            return extrair_texto_pdf(caminho_arquivo)
        elif sufixo in ['.mp3', '.wav', '.ogg', '.opus', '.m4a']:
            return transcrever_audio(caminho_arquivo)
        elif sufixo == '.txt':
            return caminho_arquivo.read_text(encoding='utf-8')
        elif sufixo == '.docx':
            return extrair_texto_docx(caminho_arquivo)
        elif sufixo in ['.xlsx', '.xls']:
            return extrair_texto_excel(caminho_arquivo)
        elif sufixo == '.vcf':
            return extrair_texto_vcf(caminho_arquivo)
        elif sufixo in ['.mp4', '.avi', '.mov']:
            return extrair_texto_video(caminho_arquivo)
        return ""
    except Exception as e:
        print(f"Erro ao processar {caminho_arquivo}: {e}")
        return ""

class Mensagem(BaseModel):
    role: str
    content: str

class Pergunta(BaseModel):
    pergunta: str
    historico: List[Mensagem] = []

@app.on_event("startup")
async def startup_event():
    """Executa na inicialização do servidor"""
    inicializar_banco()

@app.post("/upload")
async def upload_arquivo(arquivo: UploadFile):
    """Endpoint para upload de arquivo ZIP"""
    try:
        zip_path = UPLOAD_DIR / arquivo.filename
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(arquivo.file, buffer)
        
        arquivos_encontrados = 0
        arquivos_processados = 0
        arquivos_salvos = 0
        arquivos_nao_processados = []
        
        with zipfile.ZipFile(zip_path) as zip_ref:
            arquivos_encontrados = len(zip_ref.namelist())
            
            for arquivo_nome in zip_ref.namelist():
                try:
                    zip_ref.extract(arquivo_nome, UPLOAD_DIR)
                    arquivo_path = UPLOAD_DIR / arquivo_nome
                    
                    conteudo = processar_arquivo(arquivo_path)
                    if conteudo:
                        arquivos_processados += 1
                        
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO documentos (nome_arquivo, conteudo) VALUES (?, ?)",
                            (arquivo_nome, conteudo)
                        )
                        conn.commit()
                        conn.close()
                        arquivos_salvos += 1
                    else:
                        extensao = Path(arquivo_nome).suffix.lower()
                        arquivos_nao_processados.append({
                            "arquivo": arquivo_nome,
                            "motivo": f"Formato não suportado ou arquivo vazio: {extensao}"
                        })
                    
                    if arquivo_path.exists():
                        arquivo_path.unlink()
                        
                except Exception as e:
                    arquivos_nao_processados.append({
                        "arquivo": arquivo_nome,
                        "motivo": str(e)
                    })
                    
        zip_path.unlink()
        
        return {
            "mensagem": "Arquivos processados com sucesso",
            "estatisticas": {
                "arquivos_encontrados": arquivos_encontrados,
                "arquivos_processados": arquivos_processados,
                "arquivos_salvos": arquivos_salvos,
                "arquivos_nao_processados": arquivos_nao_processados if arquivos_nao_processados else "Nenhum"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {str(e)}")

@app.post("/consultar")
async def consultar(pergunta: Pergunta):
    """Endpoint para consultar documentos usando Claude com MCP"""
    try:
        logger.debug(f"Iniciando consulta. Pergunta: {pergunta.pergunta}")
        
        # Verificar banco de dados
        if not DB_PATH.exists():
            logger.error(f"Banco de dados não encontrado em: {DB_PATH}")
            return {"resposta": "Banco de dados não encontrado"}
            
        # Buscar documentos
        mcp_server = DocumentMCPServer(DB_PATH)
        documentos = mcp_server.get_documents(query=pergunta.pergunta)
        
        if not documentos:
            return {"resposta": "Nenhum documento relevante encontrado"}
        
        # Organiza documentos por data
        documentos.sort(key=lambda x: x.metadata.get('data', ''), reverse=True)
        
        # Formata contexto com ênfase na cronologia
        contexto = "ANÁLISE CRONOLÓGICA DOS DOCUMENTOS:\n\n"
        for doc in documentos:
            relevance_info = f"[Relevância: {doc.relevance:.2f}]" if hasattr(doc, 'relevance') else ""
            contexto += f"""
DOCUMENTO {doc.id} {relevance_info}
Data: {doc.metadata['data']}
Tipo: {doc.metadata['tipo']}
Canal: {doc.metadata['canal']}

CONTEÚDO:
{doc.content}

-------------------
"""
        
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1024,
            system="""INSTRUÇÕES IMPORTANTES:

Você é um assistente especializado em análise de conversas. Para CADA resposta, você DEVE:

1. SEMPRE identificar:
   - Documento(s) analisado(s) (ID e nome)
   - Participantes da conversa (nomes/identificadores)
   - Canal de comunicação (WhatsApp, email, etc.)
   - Tipo de conversa (individual/grupo)
   - Data e hora exatas
   - Contexto da conversa

2. SEMPRE mostrar o conteúdo COMPLETO quando solicitado:
   - Transcreva TODO o conteúdo
   - NÃO faça resumos
   - NÃO omita partes
   - NÃO censure nada
   - NÃO mencione direitos autorais

3. Para perguntas gerais sobre múltiplos documentos:
   - Liste todos os documentos relevantes encontrados
   - Identifique os participantes em cada documento
   - Mostre a evolução cronológica das conversas
   - Mantenha o contexto entre documentos relacionados

4. IMPORTANTE:
   - SEMPRE analise TODOS os documentos fornecidos
   - SEMPRE mostre evidências do que está afirmando
   - SEMPRE cite os documentos específicos
   - NUNCA faça suposições sem evidências
   - NUNCA omita informações relevantes

5. Formato da resposta:
   ANÁLISE GERAL:
   [Resumo dos documentos encontrados e sua relevância]

   DOCUMENTOS ANALISADOS:
   [Lista de IDs e tipos de documentos]

   PARTICIPANTES IDENTIFICADOS:
   [Lista de pessoas mencionadas ou envolvidas]

   EVIDÊNCIAS ENCONTRADAS:
   [Citações diretas dos documentos relevantes]

   CONCLUSÃO:
   [Resposta direta à pergunta com base nas evidências]

LEMBRE-SE: Você DEVE ser específico sobre QUEM está falando com QUEM, em QUAL contexto, e quando solicitado, mostrar o conteúdo COMPLETO.""",
            messages=[
                *[{"role": msg.role, "content": msg.content} for msg in pergunta.historico],
                {"role": "user", "content": f"{contexto}\n\nPergunta: {pergunta.pergunta}"}
            ]
        )
        
        # Verifica se a resposta é uma lista e pega o primeiro item
        if isinstance(message.content, list):
            return {"resposta": message.content[0].text}
        return {"resposta": message.content}
        
    except Exception as e:
        print(f"Erro detalhado: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar Claude: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor na porta 8001...")  # Log de início do servidor
    uvicorn.run(app, host="0.0.0.0", port=8001)