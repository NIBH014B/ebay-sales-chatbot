import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st  # pyright: ignore[reportMissingImports]

from agent.sales_agent import AgentChat
from services.data_service import DataService
from services.github_service import RepositoryError, purchase_repository_from_environment, repository_from_environment


APP_DIR = Path(__file__).resolve().parent
BRAND_IMAGE = APP_DIR / "assets" / "buckchi.png"
load_dotenv(APP_DIR / ".env")
os.environ.setdefault("DATA_CACHE_DIR", str(APP_DIR / ".cache" / "github"))

st.set_page_config(
    page_title="Buckchi Sales Assistant",
    page_icon=str(BRAND_IMAGE) if BRAND_IMAGE.is_file() else "✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --ink: #f4f3ef;
        --muted: #9b9d9f;
        --panel: #17191b;
        --panel-soft: #202326;
        --line: #2a2d30;
        --accent: #d4f36a;
    }

    .stApp { background: #101112; color: var(--ink); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: #151617; border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] > div:first-child { padding: 28px 20px; }
    .block-container { max-width: 1040px; padding: 32px 5vw 140px; }
    h1, h2, h3, p, label, button, input, textarea { font-family: 'DM Sans', sans-serif; }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; }
    h1 { letter-spacing: -0.04em; }
    [data-testid="stChatMessage"] { background: transparent; padding: 20px 0; }
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.7; }
    [data-testid="stChatMessage"] [data-testid="stChatMessageAvatar"] { background: var(--panel-soft); }
    [data-testid="stChatInput"] { background: var(--panel); border: 1px solid #393d40; border-radius: 18px; }
    [data-testid="stChatInput"] textarea { color: var(--ink); font-size: 15px; }
    [data-testid="stChatInput"]:focus-within { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 34px; }
    .brand-image { width: 42px; height: 42px; object-fit: contain; border-radius: 8px; }
    .brand-mark { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 10px; background: var(--accent); color: #111; font-weight: 700; }
    .brand-name { font: 700 18px 'Space Grotesk', sans-serif; color: var(--ink); }
    .eyebrow { color: var(--accent); font: 700 11px 'DM Sans', sans-serif; letter-spacing: .14em; text-transform: uppercase; }
    .hero { padding: 42px 0 22px; }
    .hero h1 { font-size: clamp(34px, 5vw, 58px); margin: 8px 0 12px; }
    .hero p { color: var(--muted); font-size: 16px; max-width: 600px; }
    .welcome { margin: 28px 0 12px; padding: 26px; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; }
    .welcome strong { color: var(--ink); font-family: 'Space Grotesk', sans-serif; font-size: 18px; }
    .welcome p { color: var(--muted); margin: 7px 0 0; }
    .side-caption { color: var(--muted); font-size: 12px; margin: 28px 0 10px; text-transform: uppercase; letter-spacing: .12em; }
    .status { color: var(--muted); font-size: 12px; padding: 14px 0; border-top: 1px solid var(--line); }
    .status span { color: var(--accent); }
    .stButton button { background: transparent; border: 1px solid var(--line); color: var(--ink); border-radius: 9px; text-align: left; }
    .stButton button:hover { border-color: var(--accent); color: var(--accent); }
    </style>
    """,
    unsafe_allow_html=True,
)


def initialize_data() -> tuple[DataService | None, str | None]:
    try:
        repository = repository_from_environment()
        purchase_repository = purchase_repository_from_environment()
        service = DataService(repository=repository, additional_repositories=[purchase_repository] if purchase_repository else [], local_dir=APP_DIR / "local_data")
        service.load()
        return service, None
    except RepositoryError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"Data setup failed ({type(exc).__name__}). Check the configuration and dataset files."


def record_count(service: DataService | None) -> int:
    if not service:
        return 0
    return sum(len(item.frame) for item in service.datasets if "sales" in item.roles)


if "messages" not in st.session_state:
    chat_id = uuid.uuid4().hex[:10]
    st.session_state.chats = {chat_id: {"title": "New conversation", "messages": [], "created_at": datetime.now().isoformat(timespec="minutes")}}
    st.session_state.active_chat_id = chat_id
    st.session_state.messages = st.session_state.chats[chat_id]["messages"]
if "chats" not in st.session_state:
    chat_id = uuid.uuid4().hex[:10]
    st.session_state.chats = {chat_id: {"title": "New conversation", "messages": [], "created_at": datetime.now().isoformat(timespec="minutes")}}
    st.session_state.active_chat_id = chat_id
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = next(iter(st.session_state.chats))
st.session_state.messages = st.session_state.chats[st.session_state.active_chat_id]["messages"]
if "data_service" not in st.session_state:
    st.session_state.data_service, st.session_state.data_error = initialize_data()
if "agent_chats" not in st.session_state:
    st.session_state.agent_chats = {}


def create_chat() -> None:
    chat_id = uuid.uuid4().hex[:10]
    st.session_state.chats[chat_id] = {"title": "New conversation", "messages": [], "created_at": datetime.now().isoformat(timespec="minutes")}
    st.session_state.active_chat_id = chat_id
    st.session_state.messages = st.session_state.chats[chat_id]["messages"]


def select_chat(chat_id: str) -> None:
    st.session_state.active_chat_id = chat_id
    st.session_state.messages = st.session_state.chats[chat_id]["messages"]

with st.sidebar:
    if BRAND_IMAGE.is_file():
        st.markdown('<div class="brand">', unsafe_allow_html=True)
        st.image(str(BRAND_IMAGE), width=42)
        st.markdown('<div class="brand-name">Buckchi</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="brand"><div class="brand-mark">✦</div>'
            '<div class="brand-name">Buckchi</div></div>',
            unsafe_allow_html=True,
        )
    if st.button("＋  New chat", use_container_width=True):
        create_chat()
        st.rerun()
    st.markdown('<div class="side-caption">Conversations</div>', unsafe_allow_html=True)
    for chat_id, chat in st.session_state.chats.items():
        label = chat["title"][:34] or "New conversation"
        if st.button(label, key=f"chat-{chat_id}", use_container_width=True):
            select_chat(chat_id)
            st.rerun()
    st.markdown('<div class="side-caption">Workspace</div>', unsafe_allow_html=True)
    st.caption("Sales intelligence")
    st.caption("Ask about orders, products, revenue, or profit")
    st.markdown(
        f'<div class="status"><span>●</span> Ready · '
        f'{record_count(st.session_state.data_service):,} sales records loaded</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.data_error:
        st.warning(st.session_state.data_error)
        if st.button("Retry data connection", use_container_width=True):
            st.session_state.pop("data_service", None)
            st.session_state.pop("data_error", None)
            st.session_state.pop("agent_chat", None)
            st.rerun()
    if st.session_state.data_service:
        for warning in st.session_state.data_service.errors:
            st.warning(warning)

if not st.session_state.messages:
    st.markdown(
        '<div class="hero"><div class="eyebrow">Sales intelligence</div>'
        '<h1>What can I help you uncover?</h1>'
        '<p>Your focused workspace for understanding the numbers behind your store.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="welcome"><strong>Welcome to Buckchi Sales Assistant</strong>'
        '<p>Ask a question in plain language and turn your sales data into a next step.</p></div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown('<div class="eyebrow">Buckchi workspace</div>', unsafe_allow_html=True)
    st.markdown(f"## {st.session_state.chats[st.session_state.active_chat_id]['title']}")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

suggestion_bank = [
    "What were the sales for 22 September 2026?",
    "Compare total sales by account",
    "How much inventory is left?",
    "Which products are out of stock?",
    "What is the buying price for SKU ",
    "Show the top products by profit",
]
draft = st.text_input("Ask about your sales data", key="draft_prompt", placeholder="Type a question...")
suggestions = [item for item in suggestion_bank if not draft.strip() or draft.casefold() in item.casefold()][:4]
if suggestions:
    suggestion_columns = st.columns(len(suggestions))
    for column, suggestion in zip(suggestion_columns, suggestions):
        with column:
            if st.button(suggestion, key=f"suggestion-{suggestion}", use_container_width=True):
                st.session_state.pending_prompt = suggestion
                st.rerun()
ask = st.button("Ask", type="primary", use_container_width=False)
pending_prompt = st.session_state.pop("pending_prompt", None)
prompt = pending_prompt or (draft if ask else "")

if prompt:
    st.session_state.chats[st.session_state.active_chat_id]["title"] = prompt[:42]
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if not st.session_state.data_service:
        response = st.session_state.data_error or "Data sources could not be initialized."
    elif not st.session_state.data_service.datasets:
        response = "No datasets are loaded. Configure GITHUB_REPO_URL or add CSV, XLSX, or JSON files to `local_data/`."
    elif not os.getenv("GOOGLE_API_KEY"):
        response = "Gemini is not configured. Add GOOGLE_API_KEY to `.env`, then restart the app."
    else:
        try:
            chat_id = st.session_state.active_chat_id
            if chat_id not in st.session_state.agent_chats:
                st.session_state.agent_chats[chat_id] = AgentChat(st.session_state.data_service, user_id=f"streamlit-user-{chat_id}", session_id=f"sales-chat-{chat_id}")
            response = asyncio.run(st.session_state.agent_chats[chat_id].ask(prompt))
        except Exception as exc:
            error_text = str(exc)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                response = "Gemini's current quota is exhausted. Wait for the retry window to reset, or enable billing/increase the Gemini API quota, then try again."
            elif "404" in error_text or "NOT_FOUND" in error_text:
                response = "The configured Gemini model is unavailable for this API key. Update GEMINI_MODEL in `.env` and restart the app."
            else:
                response = "Gemini could not complete that request. Check the API key, network connection, and server logs, then try again."
    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})