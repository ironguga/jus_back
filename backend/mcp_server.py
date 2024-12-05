from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@dataclass
class Document:
    id: str
    metadata: Dict
    content: str
    relevance: float = 0.0

class DocumentMCPServer:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        logger.debug(f"Inicializando MCP Server com banco de dados: {db_path}")
        
    def get_documents(self, query: str = None) -> List[Document]:
        """Busca documentos relevantes baseado na query"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Primeiro, vamos pegar todos os documentos
            cursor.execute("SELECT id, nome_arquivo, conteudo FROM documentos")
            all_docs = cursor.fetchall()
            conn.close()
            
            documents = []
            for doc in all_docs:
                document = Document(
                    id=str(doc[0]),
                    metadata=self._extract_metadata(doc[1]),
                    content=doc[2]
                )
                
                if query:
                    # Calcula relevância do documento para a query
                    relevance = self._calculate_relevance(document, query)
                    if relevance > 0:
                        document.relevance = relevance
                        documents.append(document)
                else:
                    documents.append(document)
            
            # Ordena por relevância se houver query, senão por data
            if query and documents:
                documents.sort(key=lambda x: (x.relevance, self._safe_date(x.metadata.get('data'))), reverse=True)
            else:
                documents.sort(key=lambda x: self._safe_date(x.metadata.get('data')), reverse=True)
            
            logger.debug(f"Encontrados {len(documents)} documentos relevantes")
            return documents
            
        except Exception as e:
            logger.error(f"Erro ao buscar documentos: {str(e)}")
            raise
    
    def _safe_date(self, date_str: Optional[str]) -> datetime:
        """Converte string de data para datetime de forma segura"""
        if not date_str:
            return datetime.min
        try:
            return datetime.fromisoformat(date_str)
        except:
            return datetime.min
    
    def _calculate_relevance(self, document: Document, query: str) -> float:
        """Calcula a relevância do documento para a query"""
        relevance = 0.0
        query_terms = query.lower().split()
        
        # Procura por nomes próprios na query
        names = re.findall(r'[A-Z][a-z]+', query)
        if names:
            query_terms.extend([name.lower() for name in names])
        
        content = document.content.lower()
        
        # Verifica menções diretas
        for term in query_terms:
            if term in content:
                relevance += 1.0
                # Bonus para menções próximas de outros termos
                for other_term in query_terms:
                    if other_term != term and abs(content.find(term) - content.find(other_term)) < 100:
                        relevance += 0.5
        
        # Bonus para documentos mais recentes
        date_str = document.metadata.get('data')
        if date_str:
            try:
                date = self._safe_date(date_str)
                if date != datetime.min:
                    days_old = (datetime.now() - date).days
                    relevance += max(0, 1 - (days_old / 365))
            except Exception as e:
                logger.error(f"Erro ao processar data: {e}")
        
        # Bonus para tipos específicos de documento
        doc_type = document.metadata.get('tipo', '').lower()
        if 'audio' in doc_type:
            relevance *= 1.2  # Prioriza áudios
        
        return relevance
    
    def _extract_metadata(self, filename: str) -> Dict:
        """Extrai metadados do nome do arquivo"""
        logger.debug(f"Extraindo metadados do arquivo: {filename}")
        
        try:
            parts = filename.split('-')
            
            if len(parts) >= 4:
                date_str = f"{parts[2]}-{parts[3]}-{parts[4]}"
                time_str = f"{parts[5]}-{parts[6]}-{parts[7]}" if len(parts) > 7 else "00-00-00"
                timestamp = datetime.strptime(f"{date_str} {time_str.replace('.opus', '')}", "%Y-%m-%d %H-%M-%S")
            else:
                timestamp = datetime.now()
        except Exception as e:
            logger.error(f"Erro ao extrair timestamp: {str(e)}")
            timestamp = datetime.now()

        metadata = {
            "nome": filename,
            "tipo": self._get_tipo_documento(filename),
            "data": timestamp.isoformat(),
            "canal": self._get_canal(filename),
            "tipo_conversa": "Mensagem Individual" if "AUDIO" in filename else "Não especificado"
        }
        logger.debug(f"Metadados extraídos: {metadata}")
        return metadata
    
    def _get_tipo_documento(self, nome: str) -> str:
        if "AUDIO" in nome: return "Transcrição de áudio"
        if "PHOTO" in nome: return "Texto extraído de imagem"
        if "VIDEO" in nome: return "Transcrição de vídeo"
        if nome.endswith(".pdf"): return "PDF"
        if nome.endswith(".docx"): return "Documento Word"
        if nome.endswith((".xlsx", ".xls")): return "Planilha Excel"
        if nome.endswith(".vcf"): return "Arquivo de contato"
        return "Outro"
    
    def _get_canal(self, nome: str) -> str:
        if "AUDIO" in nome: return "WhatsApp (Áudio)"
        if "PHOTO" in nome: return "WhatsApp (Imagem)"
        if "VIDEO" in nome: return "WhatsApp (Vídeo)"
        return "Arquivo Local" 