import csv
from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]


st.set_page_config(
    page_title="Buckchi Sales Assistant",
    page_icon="✦",
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


def load_sales_rows() -> list[dict[str, str]]:
    """Load the first CSV dataset found beside this app, when available."""
    data_path = Path(__file__).parent / "data"
    if not data_path.is_dir():
        return []
    csv_files = sorted(data_path.glob("*.csv"))
    if not csv_files:
        return []
    with csv_files[0].open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def answer_sales_question(question: str, rows: list[dict[str, str]]) -> str:
    question_lower = question.lower()
    if not rows:
        return (
            "I’m ready to analyze your sales. Add a CSV export to the `data` "
            "folder and I’ll use it for revenue, order, product, and profit "
            "questions. For now, I can help you plan metrics, clean an export, "
            "or design a sales report."
        )

    if "how many" in question_lower or "orders" in question_lower:
        return f"I found **{len(rows):,} sales records** in your dataset."
    if "column" in question_lower or "field" in question_lower:
        columns = ", ".join(f"`{column}`" for column in rows[0])
        return f"Your dataset includes: {columns}."
    return (
        f"I found **{len(rows):,} records**. I can summarize order volume and "
        "inspect the available fields. Try asking, ‘How many orders do I have?’"
    )


if "messages" not in st.session_state:
    st.session_state.messages = []
if "sales_rows" not in st.session_state:
    st.session_state.sales_rows = load_sales_rows()

with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">✦</div>'
        '<div class="brand-name">Buckchi</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("＋  New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.markdown('<div class="side-caption">Workspace</div>', unsafe_allow_html=True)
    st.caption("Sales intelligence")
    st.caption("Ask about orders, products, revenue, or profit")
    st.markdown(
        f'<div class="status"><span>●</span> Ready · '
        f'{len(st.session_state.sales_rows):,} records loaded</div>',
        unsafe_allow_html=True,
    )

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
    starter_prompts = [
        "How many orders do I have?",
        "Show me the fields in my sales data",
        "What should I track in a weekly report?",
    ]
    prompt_columns = st.columns(3)
    for column, starter in zip(prompt_columns, starter_prompts):
        with column:
            if st.button(starter, use_container_width=True):
                st.session_state.pending_prompt = starter
                st.rerun()
else:
    st.markdown('<div class="eyebrow">Buckchi workspace</div>', unsafe_allow_html=True)
    st.markdown("## Sales Assistant")

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="✦" if message["role"] == "assistant" else "✎"):
        st.markdown(message["content"])

prompt = st.chat_input("Message Buckchi...")
pending_prompt = st.session_state.pop("pending_prompt", None)
prompt = prompt or pending_prompt

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="✎"):
        st.markdown(prompt)

    response = answer_sales_question(prompt, st.session_state.sales_rows)
    with st.chat_message("assistant", avatar="✦"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})