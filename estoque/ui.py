import streamlit as st

def header(title: str, subtitle: str = ""):
    st.title(title)
    if subtitle:
        st.write(subtitle)

def status_badge(text: str, status: str):
    colors = {"ok": "green", "low": "red"}
    color = colors.get(status, "gray")
    st.markdown(f"<span style='color:{color}; font-weight:bold;'>{text}</span>", unsafe_allow_html=True)
