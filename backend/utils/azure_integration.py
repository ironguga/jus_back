import os
import logging
import base64
import httpx

logger = logging.getLogger(__name__)

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

def gerar_chave_valida(original: str) -> str:
    return base64.urlsafe_b64encode(original.encode('utf-8')).decode('utf-8')

async def index_in_azure_search(content_data: dict):
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_INDEX or not AZURE_SEARCH_API_KEY:
        logger.error("Configurações de Azure Search não definidas corretamente.")
        return

    doc_id_original = content_data['metadata'].get('file_name', 'doc_sem_nome')
    doc_id = gerar_chave_valida(doc_id_original)
    file_type = content_data['metadata'].get('file_type', '')
    file_name = content_data['metadata'].get('file_name', 'desconhecido')
    summary = content_data['metadata'].get('summary', '')

    doc = {
        "value": [
            {
                "@search.action": "upload",
                "id": doc_id,
                "content": content_data['content'],
                "file_type": file_type,
                "file_name": file_name,
                "processed": True,
                "summary": summary
            }
        ]
    }

    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/index?api-version=2021-04-30-Preview"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=doc, headers=headers)
            response.raise_for_status()
            logger.info(f"Documento {doc_id_original} (id: {doc_id}) indexado com sucesso no Azure Search.")
        except httpx.HTTPError as e:
            logger.error(f"Falha ao indexar o documento {doc_id_original} (id: {doc_id}): {response.status_code} {response.text}")
            logger.exception(e)

async def search_in_azure(query: str, skip: int = 0, top: int = 5):
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_INDEX or not AZURE_SEARCH_API_KEY:
        logger.error("Configurações de Azure Search não definidas para busca.")
        return {"results": [], "total_count": 0}

    from urllib.parse import quote
    safe_query = quote(query)
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs?api-version=2021-04-30-Preview&search={safe_query}&$top={top}&$skip={skip}&$count=true"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = None
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            results = response.json()
            docs = results.get('value', [])
            total_count = results.get('@odata.count', 0)
            documentos = []
            for d in docs:
                documentos.append({
                    "id": d.get('id', ''),
                    "file_name": d.get('file_name', 'desconhecido'),
                    "file_type": d.get('file_type', ''),
                    "content": d.get('content', ''),
                    "summary": d.get('summary', '')
                })
            return {"results": documentos, "total_count": total_count}
        except httpx.HTTPError as e:
            logger.error(f"Erro ao buscar no Azure Search: {e}")
            if response is not None:
                logger.error(f"Status code: {response.status_code}, Resposta: {response.text}")
            logger.exception(e)
            return {"results": [], "total_count": 0}

async def azure_gpt_chat_completion(query: str, context: str = "") -> str:
    messages = []
    if context:
        messages.append({"role": "system", "content": f"Contexto:\n\n{context}"})
    messages.append({"role": "user", "content": query})

    logger.info(f"Enviando requisição ao Azure OpenAI - Endpoint: {AZURE_OPENAI_ENDPOINT}, Deployment: {AZURE_OPENAI_DEPLOYMENT_NAME}, Versão: {AZURE_OPENAI_API_VERSION}")
    logger.info(f"Mensagens enviadas: {messages}")

    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_NAME}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 1024,
        "frequency_penalty": 0,
        "presence_penalty": 0
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = None
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            resp_json = response.json()

            logger.info(f"Resposta HTTP do Azure OpenAI: {response.status_code}, {response.text[:500]}...")

            if "choices" in resp_json and len(resp_json["choices"]) > 0:
                resposta = resp_json["choices"][0]["message"]["content"]
                logger.info(f"Resposta do modelo: {resposta}")
                return resposta.strip()
            else:
                logger.info("Modelo não retornou escolhas.")
                return "Não consegui gerar uma resposta."
        except httpx.HTTPError as e:
            logger.error(f"Erro ao consultar Azure GPT: {e}")
            if response is not None:
                logger.error(f"Código HTTP: {response.status_code}, Resposta: {response.text}")
            logger.exception(e)
            return f"Erro ao processar consulta: {str(e)}"