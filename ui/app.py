"""Interfaz de chat de Centy, el asistente virtual de Mercado Central 24h.

Dos modos, elegidos explicitamente por el usuario en el panel lateral (no se
infiere automaticamente): "Documentos" llama a /chat/documentos (RAG sobre
politicas y procedimientos) e "Inventario" llama a /chat/inventario (consulta
estructurada con pandas). Ver app/main.py para el porque de esta separacion.
"""

import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

SUGERENCIAS_DOCUMENTOS = [
    "¿A qué hora debe estar terminado el surtido nocturno?",
    "¿Cómo se debe aplicar el sistema PEPS en la sección de lácteos?",
    "Mi turno es nocturno, ¿cuántas horas debo trabajar y cuándo es mi descanso?",
    "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?",
    "Se está quemando algo en la sección de panadería. ¿Cuáles son los pasos a seguir?",
    "Vi a un cliente metiendo productos en su bolsa sin pagar. ¿Cuál es el protocolo?",
    "¿Cuál es el proceso para levantar un acta administrativa?",
]

SUGERENCIAS_INVENTARIO = [
    "¿Qué productos están bajo el stock mínimo?",
    "¿Qué productos vencen en los próximos 30 días?",
    "¿Qué productos tenemos en la categoría de lácteos?",
    "¿En qué pasillo se encuentra el arroz?",
]

MODOS = {
    "📄 Documentos": {
        "endpoint": "/chat/documentos",
        "sugerencias": SUGERENCIAS_DOCUMENTOS,
        "placeholder": "Pregunta sobre políticas, procedimientos o emergencias...",
    },
    "📦 Inventario": {
        "endpoint": "/chat/inventario",
        "sugerencias": SUGERENCIAS_INVENTARIO,
        "placeholder": "Pregunta sobre stock, precios o ubicación de productos...",
    },
}

st.set_page_config(page_title="Centy — Mercado Central 24h", page_icon="🌙", layout="wide")

if "historiales" not in st.session_state:
    st.session_state.historiales = {modo: [] for modo in MODOS}
if "pregunta_pendiente" not in st.session_state:
    st.session_state.pregunta_pendiente = None

with st.sidebar:
    st.title("🌙 Centy")
    st.caption("Asistente virtual — Mercado Central 24h")
    modo = st.radio("¿Sobre qué quieres preguntar?", list(MODOS.keys()))
    st.divider()
    st.subheader("Preguntas sugeridas")
    for sugerencia in MODOS[modo]["sugerencias"]:
        if st.button(sugerencia, use_container_width=True, key=f"sug_{modo}_{sugerencia}"):
            st.session_state.pregunta_pendiente = sugerencia

st.title("🌙 Centy")
st.caption(
    "Asistente virtual para la empresa Mercado Central 24h. Responde con base en las "
    "políticas, procedimientos e inventario internos — nunca inventa información."
)

historial = st.session_state.historiales[modo]

for mensaje in historial:
    with st.chat_message(mensaje["role"]):
        st.markdown(mensaje["content"])

pregunta = st.chat_input(MODOS[modo]["placeholder"])
if st.session_state.pregunta_pendiente:
    pregunta = st.session_state.pregunta_pendiente
    st.session_state.pregunta_pendiente = None

if pregunta:
    historial.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        with st.spinner("Centy está pensando..."):
            try:
                resp = requests.post(
                    f"{API_BASE_URL}{MODOS[modo]['endpoint']}",
                    json={"pregunta": pregunta},
                    timeout=120,
                )
                resp.raise_for_status()
                respuesta = resp.json()["respuesta"]
            except requests.RequestException as exc:
                respuesta = (
                    "No pude conectarme con el servidor del agente. "
                    f"¿Está corriendo la API en {API_BASE_URL}? (detalle: {exc})"
                )
        st.markdown(respuesta)
    historial.append({"role": "assistant", "content": respuesta})
