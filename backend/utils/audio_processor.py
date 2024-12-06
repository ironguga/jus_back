import logging
import asyncio
import whisper
from pathlib import Path
import os
import time
import speech_recognition as sr
from moviepy.editor import VideoFileClip
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self):
        self.model = None
        self._initialized = False
        self.recognizer = sr.Recognizer()
        self.supported_audio_extensions = {'wav', 'mp3', 'ogg', 'm4a'}
        self.supported_video_extensions = {'mp4', 'avi', 'mkv', 'mov'}

    async def initialize(self):
        if self._initialized:
            logger.debug("Modelo Whisper já inicializado, pulando...")
            return
            
        logger.info("Iniciando carregamento do modelo Whisper (versão: base)...")
        try:
            start_time = time.time()
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(None, whisper.load_model, "base")
            self._initialized = True
            load_time = time.time() - start_time
            logger.info(f"Modelo Whisper carregado com sucesso em {load_time:.2f} segundos")
        except Exception as e:
            logger.error(f"Erro crítico ao carregar modelo Whisper: {e}", exc_info=True)
            raise

    async def process_media(self, file_path: Path) -> Dict[str, Any]:
        """Processa arquivo de áudio ou vídeo e retorna a transcrição"""
        try:
            extension = file_path.suffix.lower()[1:]
            
            if extension in self.supported_video_extensions:
                audio_path = await self._extract_audio_from_video(file_path)
                return await self._transcribe_audio(audio_path)
            
            elif extension in self.supported_audio_extensions:
                return await self._transcribe_audio(file_path)
            
            else:
                logger.warning(f"Formato não suportado: {extension}")
                return {"error": "Formato não suportado"}

        except Exception as e:
            logger.error(f"Erro ao processar mídia {file_path}: {str(e)}")
            return {"error": str(e)}

    async def _extract_audio_from_video(self, video_path: Path) -> Path:
        """Extrai áudio de um arquivo de vídeo"""
        try:
            audio_path = video_path.parent / f"{video_path.stem}_audio.wav"
            video = VideoFileClip(str(video_path))
            video.audio.write_audiofile(str(audio_path))
            video.close()
            return audio_path
        except Exception as e:
            logger.error(f"Erro ao extrair áudio do vídeo: {str(e)}")
            raise

    async def _transcribe_audio(self, audio_path: Path) -> Dict[str, Any]:
        """Transcreve um arquivo de áudio"""
        try:
            with sr.AudioFile(str(audio_path)) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio, language='pt-BR')
                
                return {
                    "type": "audio",
                    "content": text,
                    "metadata": {
                        "file_type": audio_path.suffix[1:],
                        "file_name": audio_path.name
                    }
                }
        except Exception as e:
            logger.error(f"Erro na transcrição do áudio: {str(e)}")
            raise