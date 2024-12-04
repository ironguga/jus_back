import whisper
from pathlib import Path

def transcrever_audio(caminho_arquivo: Path) -> str:
    """Transcreve um arquivo de áudio usando Whisper"""
    try:
        model = whisper.load_model("base")  # ou "small", "medium", "large"
        result = model.transcribe(str(caminho_arquivo))
        return result["text"]
    except Exception as e:
        print(f"Erro ao transcrever áudio: {e}")
        return "" 