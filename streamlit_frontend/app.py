import streamlit as st
import requests

API_BASE = "http://localhost:8001"  # Ajuste conforme necessário
USER_ID = "usuario123"

st.set_page_config(page_title="Chat com Contexto (Streamlit)", page_icon="💬")

# CSS customizado para visual mais agradável
st.markdown("""
<style>
body {
    font-family: "Arial", sans-serif;
}

h1 {
    text-align: center;
    margin-bottom: 10px;
}

/* Ajuste no container para centralizar */
.block-container {
    max-width: 600px;
    margin: auto;
    padding-top: 20px;
}
</style>
""", unsafe_allow_html=True)

# Inicializa o estado se não existir
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Olá! Como posso ajudar?"}
    ]

def build_historico_for_api():
    # Histórico no formato {role: 'assistant'|'user', content: str}
    return st.session_state.messages

def send_message_to_api(pergunta):
    historico = build_historico_for_api()
    payload = {"pergunta": pergunta, "historico": historico}
    try:
        # Logs de debug
        st.write("DEBUG - Enviando payload para /consultar:", payload)
        resp = requests.post(f"{API_BASE}/consultar", json=payload, timeout=60)
        st.write("DEBUG - Status code /consultar:", resp.status_code)
        st.write("DEBUG - Resposta bruta /consultar:", resp.text)
        resp.raise_for_status()
        data = resp.json()
        resposta = data.get("resposta", "Não obtive resposta.")
        st.write("DEBUG - Resposta final obtida da API:", resposta)
        return resposta
    except Exception as e:
        st.write("DEBUG - Erro na chamada /consultar:", str(e))
        return f"Erro ao consultar: {str(e)}"

def upload_file_to_api(file):
    files = {
        "file": (file.name, file.getvalue(), file.type if file.type else "application/octet-stream")
    }
    try:
        st.write("DEBUG - Fazendo upload do arquivo:", file.name)
        resp = requests.post(f"{API_BASE}/upload", files=files, timeout=20)
        st.write("DEBUG - Status code /upload:", resp.status_code)
        st.write("DEBUG - Resposta bruta /upload:", resp.text)
        resp.raise_for_status()
        data = resp.json()
        msg = f"Upload finalizado: {data.get('estatisticas', data)}"
        st.write("DEBUG - Mensagem de upload processada:", msg)
        return msg
    except Exception as e:
        st.write("DEBUG - Erro na chamada /upload:", str(e))
        return f"Erro no upload: {str(e)}"

st.title("💬 Chat com Contexto (Streamlit)")
st.write("Esse chat conversa com o backend, mantém histórico, permite upload de arquivos e mostra logs de debug.")

# Upload de arquivo
uploaded_file = st.file_uploader("Selecione um arquivo para enviar:")
if uploaded_file is not None:
    if st.button("Enviar Arquivo"):
        st.write("DEBUG - Botão Enviar Arquivo clicado")
        msg_upload = upload_file_to_api(uploaded_file)
        st.session_state.messages.append({"role": "assistant", "content": msg_upload})
        # Após adicionar mensagem ao histórico, a página reroda,
        # as mensagens serão exibidas no final do código.

st.divider()

# Exibir histórico ANTES do input do usuário não seria ideal. Vamos exibir depois de tudo.

# Campo de entrada do usuário (chat)
user_input = st.chat_input("Digite sua mensagem...")
if user_input:
    st.write("DEBUG - Usuário digitou mensagem:", user_input)
    # Mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": user_input})
    # Chama API e obtem resposta
    resposta = send_message_to_api(user_input)
    st.session_state.messages.append({"role": "assistant", "content": resposta})
    # Quando o usuário envia a mensagem, o st.chat_input faz o rerun automaticamente.

# Agora, após toda a lógica (upload e envio de msg), exibimos o histórico de mensagens.
# Assim garantimos que a última mensagem adicionada seja exibida.
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])