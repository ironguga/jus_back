import fitz  # PyMuPDF
from docx import Document  # pip install python-docx
import pandas as pd       # pip install pandas
import vobject           # pip install vobject
import cv2              # pip install opencv-python
from .ocr import extrair_texto_imagem

def extrair_texto_pdf(caminho_arquivo):
    """
    Extrai texto de um arquivo PDF
    """
    try:
        doc = fitz.open(caminho_arquivo)
        texto = ""
        for pagina in doc:
            texto += pagina.get_text()
        return texto
    except Exception as e:
        print(f"Erro ao processar PDF {caminho_arquivo}: {str(e)}")
        return "" 

def extrair_texto_docx(caminho_arquivo):
    """Extrai texto de arquivos .docx"""
    try:
        doc = Document(caminho_arquivo)
        return " ".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        print(f"Erro ao processar DOCX: {e}")
        return ""

def extrair_texto_excel(caminho_arquivo):
    """Extrai texto de arquivos Excel"""
    try:
        df = pd.read_excel(caminho_arquivo)
        return df.to_string()
    except Exception as e:
        print(f"Erro ao processar Excel: {e}")
        return ""

def extrair_texto_vcf(caminho_arquivo):
    """Extrai informações de arquivos VCF (contatos)"""
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            vcard = vobject.readOne(f.read())
            info = []
            if hasattr(vcard, 'fn'): info.append(f"Nome: {vcard.fn.value}")
            if hasattr(vcard, 'tel'): info.append(f"Telefone: {vcard.tel.value}")
            if hasattr(vcard, 'email'): info.append(f"Email: {vcard.email.value}")
            return " | ".join(info)
    except Exception as e:
        print(f"Erro ao processar VCF: {e}")
        return ""

def extrair_texto_video(caminho_arquivo):
    """Extrai frames de vídeo e processa com OCR"""
    try:
        video = cv2.VideoCapture(str(caminho_arquivo))
        textos = []
        while video.isOpened():
            ret, frame = video.read()
            if not ret:
                break
            # Processar frame com OCR
            texto = extrair_texto_imagem(frame)
            if texto:
                textos.append(texto)
        video.release()
        return " ".join(textos)
    except Exception as e:
        print(f"Erro ao processar vídeo: {e}")
        return "" 