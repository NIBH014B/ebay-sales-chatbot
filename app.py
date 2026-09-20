import streamlit as st  # pyright: ignore[reportMissingImports]

st.set_page_config(
    page_title="eBay Sales Assistant",
    page_icon="💬",
    layout="wide"
)

st.title("💬 eBay Sales Assistant")

st.write(
    "Ask questions about your eBay sales, revenue, orders, "
    "products and profit."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ask something about your eBay sales...")

if prompt:
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    response = (
        "I received your question. "
        "The eBay data agent will be connected next."
    )

    with st.chat_message("assistant"):
        st.markdown(response)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response
    })