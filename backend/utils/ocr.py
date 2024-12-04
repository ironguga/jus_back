import cv2
import pytesseract
from pathlib import Path

def extrair_texto_imagem(imagem):
    try:
        if isinstance(imagem, (str, Path)):
            imagem = cv2.imread(str(imagem))
        gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        texto = pytesseract.image_to_string(gray, lang='por')
        return texto.strip()
    except Exception as e:
        print(f"Erro no OCR: {e}")
        return "" 