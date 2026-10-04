import os
import time
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    page_icon="⚡",
    layout="wide"
)

# Credenciais do Supabase via Streamlit Secrets ou Variáveis de Ambiente
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", "")).strip().rstrip("/")
if SUPABASE_URL and not SUPABASE_URL.startswith("http"):
    SUPABASE_URL = f"https://{SUPABASE_URL}"

SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", "")).strip()

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -----------------------------------------------------------------------------
# 2. FUNÇÕES DE SUPORTE (API & SUPABASE)
# -----------------------------------------------------------------------------
def fetch_dexscreener_data(pair_address):
    """Obtém preço atual via DexScreener usando o Pair Address."""
    if not pair_address or len(str(pair_address).strip()) < 5:
        return None, None
    url = f"https://api.dexscreener.com/latest/dex/search?q={str(pair_address).strip()}"
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data and "pairs" in data and len(data["pairs"]) > 0:
                pair = data["pairs"][0]
                return float(pair.get("priceUsd", 0)), float(pair.get("priceNative", 0))
    except Exception as eComo não especificaste a qual código te referes, envia-me por favor mais detalhes sobre o projeto ou a tarefa em questão. 

Se precisas do código completo de um projeto específico, indica:
* **A linguagem de programação ou framework** (ex.: Python, JavaScript, HTML/CSS, React, etc.)
* **O objetivo do código** (ex.: um script de scraping, uma página Web, um cálculo específico)
* **Requisitos ou funcionalidades adicionais** que deve conter.
