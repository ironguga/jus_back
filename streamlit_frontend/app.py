import streamlit as st
import requests

API_BASE = "http://localhost:8001"
USER_ID = "usuario123"

st.set_page_config(page_title="Chat com Contexto (Streamlit)", page_icon="💬")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Olá! Como posso ajudar?"}
    ]
if "skip" not in st.session_state:
    st.session_state.skip = 0
if "top" not in st.session_state:
    st.session_state.top = 2
if "total_count" not in st.session_state:
    st.session_state.total_count = 0

def build_historico_for_api():
    return st.session_state.messages

def send_message_to_api(pergunta, skip=0, top=2):
    historico = build_historico_for_api()
    payload = {"pergunta": pergunta, "historico": historico}
    params = {"skip": skip, "top": top}
    try:
        resp = requests.post(f"{API_BASE}/consultar", json=payload, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        resposta = data.get("resposta", "Não obtive resposta.")
        st.session_state.total_count = data.get("total_count", 0)
        return resposta
    except Exception as e:
        return f"Erro ao consultar: {str(e)}"

def upload_file_to_api(file):
    files = {
        "file": (file.name, file.getvalue(), file.type if file.type else "application/octet-stream")
    }
    try:
        resp = requests.post(f"{API_BASE}/upload", files=files, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        msg = f"Upload finalizado: {data.get('estatisticas', data)}"
        return msg
    except Exception as e:
        return f"Erro no upload: {str(e)}"

st.title("💬 Chat com Contexto (Streamlit)")

# Upload de arquivo
uploaded_file = st.file_uploader("Selecione um arquivo para enviar:")
if uploaded_file is not None:
    if st.button("Enviar Arquivo"):
        msg_upload = upload_file_to_api(uploaded_file)
        st.session_state.messages.append({"role": "assistant", "content": msg_upload})

st.divider()

# Controles de paginação
col1, col2 = st.columns(2)
with col1:
    if st.button("Página Anterior"):
        if st.session_state.skip - st.session_state.top >= 0:
            st.session_state.skip -= st.session_state.top
with col2:
    if st.button("Próxima Página"):
        if st.session_state.skip + st.session_state.top < st.session_state.total_count:
            st.session_state.skip += st.session_state.top

# Campo de entrada do usuário
user_input = st.chat_input("Digite sua mensagem...")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    resposta = send_message_to_api(user_input, skip=st.session_state.skip, top=st.session_state.top)
    st.session_state.messages.append({"role": "assistant", "content": resposta})

# Exibir histórico
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])