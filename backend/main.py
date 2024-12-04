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
    """Endpoint para consultar documentos usando Claude"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Contar total de documentos e tipos
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN nome_arquivo LIKE '%AUDIO%' THEN 1 ELSE 0 END) as audios,
                SUM(CASE WHEN nome_arquivo LIKE '%PHOTO%' THEN 1 ELSE 0 END) as fotos,
                SUM(CASE WHEN nome_arquivo LIKE '%VIDEO%' THEN 1 ELSE 0 END) as videos,
                SUM(CASE WHEN nome_arquivo LIKE '%.pdf' THEN 1 ELSE 0 END) as pdfs,
                SUM(CASE WHEN nome_arquivo LIKE '%.docx' THEN 1 ELSE 0 END) as docs,
                SUM(CASE WHEN nome_arquivo LIKE '%.xlsx' OR nome_arquivo LIKE '%.xls' THEN 1 ELSE 0 END) as planilhas,
                SUM(CASE WHEN nome_arquivo LIKE '%.vcf' THEN 1 ELSE 0 END) as contatos,
                SUM(CASE 
                    WHEN nome_arquivo NOT LIKE '%AUDIO%' 
                    AND nome_arquivo NOT LIKE '%PHOTO%'
                    AND nome_arquivo NOT LIKE '%VIDEO%'
                    AND nome_arquivo NOT LIKE '%.pdf'
                    AND nome_arquivo NOT LIKE '%.docx'
                    AND nome_arquivo NOT LIKE '%.xlsx'
                    AND nome_arquivo NOT LIKE '%.xls'
                    AND nome_arquivo NOT LIKE '%.vcf'
                    THEN 1 ELSE 0 END) as outros
            FROM documentos
        """)
        stats = cursor.fetchone()
        total, audios, fotos, videos, pdfs, docs, planilhas, contatos, outros = stats
        
        # Criar descrição dos tipos de documentos
        tipos_desc = []
        if audios > 0: tipos_desc.append(f"{audios} transcrições de áudio")
        if fotos > 0: tipos_desc.append(f"{fotos} textos extraídos de imagens")
        if videos > 0: tipos_desc.append(f"{videos} transcrições de vídeo")
        if pdfs > 0: tipos_desc.append(f"{pdfs} PDFs")
        if docs > 0: tipos_desc.append(f"{docs} documentos Word")
        if planilhas > 0: tipos_desc.append(f"{planilhas} planilhas Excel")
        if contatos > 0: tipos_desc.append(f"{contatos} arquivos de contato")
        if outros > 0: tipos_desc.append(f"{outros} outros tipos de arquivo")

        tipos_str = ", ".join(tipos_desc[:-1]) + (" e " + tipos_desc[-1] if tipos_desc else "")
        
        # Buscar os documentos com ID
        cursor.execute("SELECT id, nome_arquivo, conteudo FROM documentos ORDER BY id")
        documentos = cursor.fetchall()
        conn.close()

        # Criar contexto dos documentos
        contexto = "\n\n".join([
            f"[Documento #{doc[0]} - {doc[1]}]:\n{doc[2]}" 
            for doc in documentos
        ])

        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1024,
            system=f"""Você é um assistente amigável especializado em análise de conversas e documentos. Você tem acesso a {total} documentos, incluindo {tipos_str}.

Aqui está o conteúdo dos documentos:

{contexto}

Lembre-se:
1. Mantenha o contexto da nossa conversa atual
2. Se eu fizer referência a algo que discutimos antes, use esse contexto
3. Identifique sempre: remetente, destinatário, tipo de conversa e canal
4. Cite as fontes naturalmente
5. Seja amigável e conversacional""",
            messages=[
                *[{"role": msg.role, "content": msg.content} for msg in pergunta.historico],
                {"role": "user", "content": pergunta.pergunta}
            ]
        )
        return {"resposta": message.content[0].text}
    except Exception as e:
        print(f"Erro detalhado: {str(e)}")  # Log para debug
        raise HTTPException(status_code=500, detail=f"Erro ao consultar Claude: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor na porta 8001...")  # Log de início do servidor
    uvicorn.run(app, host="0.0.0.0", port=8001)