import os
import time
import math
import random
import base64
import struct
from datetime import datetime, date
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA & CSS RESPONSIVO
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="DeFi Liquidity Hub Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    .pool-card {
        background-color: #1a1f2c;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #2d3748;
        margin-bottom: 12px;
    }
    .pool-card-active { border-left: 5px solid #10b981; }
    .pool-card-inactive { border-left: 5px solid #ef4444; }
    .pool-card-closed { border-left: 5px solid #6b7280; opacity: 0.65; }
    
    .badge-active {
        background-color: rgba(16, 185, 129, 0.2);
        color: #10b981;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-inactive {
        background-color: rgba(239, 68, 68, 0.2);
        color: #ef4444;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-closed {
        background-color: rgba(107, 114, 128, 0.2);
        color: #9ca3af;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.8rem;
    }

    @media (max-width: 768px) {
        div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
        div[data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
        .pool-card { padding: 10px; }
        h3 { font-size: 1.1rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. CREDENCIAIS & SECRETS
# -----------------------------------------------------------------------------
def get_secret(key_names, default=""):
    if isinstance(key_names, str):
        key_names = [key_names]
    for name in key_names:
        try:
            if name in st.secrets:
                val = str(st.secrets[name]).strip()
                if val:
                    return val
        except Exception:
            pass
        env_val = str(os.environ.get(name, "")).strip()
        if env_val:
            return env_val
    return default

SUPABASE_URL = get_secret("SUPABASE_URL").rstrip("/")
if SUPABASE_URL and not SUPABASE_URL.startswith("http"):
    SUPABASE_URL = f"https://{SUPABASE_URL}"

SUPABASE_KEY = get_secret("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = get_secret(["TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"])
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")
SOLANA_RPC_URL = get_secret("SOLANA_RPC_URL")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -----------------------------------------------------------------------------
# 3. FUNÇÕES AUXILIARES, HELIUS RPC & DEFILLAMA
# -----------------------------------------------------------------------------
def normalizar_estado(estado_raw):
    e = str(estado_raw or "").strip().lower()
    if "fechad" in e or "closed" in e:
        return "Fechada"
    elif "inativ" in e or "fora" in e:
        return "Inativa"
    return "Ativa"

def send_telegram(message):
    bot_token = get_secret(["TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"])
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=8)
        return res.status_code == 200
    except Exception:
        return False

def fetch_dexscreener_data(pair_address):
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
    except Exception:
        pass
    return None, None

def fetch_raydium_clmm_pending_fees(position_pubkey, price_usd=1.0):
    """
    Lê os dados da posição na Solana via Helius RPC de forma 100% segura (Read-Only).
    """
    if not SOLANA_RPC_URL or not position_pubkey or len(str(position_pubkey).strip()) < 20:
        return 0.0

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            str(position_pubkey).strip(),
            {"encoding": "base64"}
        ]
    }
    try:
        res = requests.post(SOLANA_RPC_URL, json=payload, timeout=8)
        if res.status_code == 200:
            val = res.json().get("result", {}).get("value")
            if not val or "data" not in val:
                return 0.0
            
            raw_data = base64.b64decode(val["data"][0])
            if len(raw_data) >= 120:
                fees_a_raw = struct.unpack_from("<Q", raw_data, offset=104)[0]
                fees_b_raw = struct.unpack_from("<Q", raw_data, offset=112)[0]
                fees_a = fees_a_raw / 1e6
                fees_b = fees_b_raw / 1e6
                return (fees_a * price_usd) + fees_b
    except Exception:
        pass
    return 0.0

@st.cache_data(ttl=3600)
def fetch_defillama_yields():
    url = "https://yields.llama.fi/pools"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception:
        pass
    return []

def render_sparkline_chart(preco_atual, range_min, range_max):
    if preco_atual <= 0:
        return
    
    steps = 15
    x_vals = list(range(steps))
    y_vals = []
    for i in range(steps):
        factor = 1.0 + ((i - steps) * 0.002) + (random.uniform(-0.005, 0.005))
        y_vals.append(preco_atual * factor)
    y_vals[-1] = preco_atual

    fig = go.Figure()

    if range_min > 0:
        fig.add_hline(y=range_min, line_dash="dash", line_color="#ef4444", line_width=1)
    if range_max > 0:
        fig.add_hline(y=range_max, line_dash="dash", line_color="#ef4444", line_width=1)

    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode="lines",
        line=dict(color="#10b981", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(16, 185, 129, 0.12)",
        hoverinfo="y"
    ))

    fig.update_layout(
        margin=dict(l=0, r=0, t=5, b=5),
        height=65,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def get_pools():
    url = f"{SUPABASE_URL}/rest/v1/pools?select=*&order=id.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def get_historico_pnl():
    url = f"{SUPABASE_URL}/rest/v1/historico_pnl?select=*&order=data.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def to_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def format_crypto_price(val):
    v = to_float(val)
    if v == 0:
        return "0.00"
    elif v < 0.001:
        return f"{v:.8f}"
    elif v < 1:
        return f"{v:.6f}"
    else:
        return f"{v:.4f}"

def calcular_dias_metricas(data_str, horas_inativa):
    if not data_str:
        return 1.0, 1.0
    try:
        data_inicio = datetime.strptime(str(data_str).strip(), "%Y-%m-%d").date()
        dias_corridos = max((date.today() - data_inicio).days, 1)
        dias_inativos = to_float(horas_inativa) / 24.0
        dias_ativos = max(dias_corridos - dias_inativos, 0.1)
        return float(dias_corridos), float(dias_ativos)
    except Exception:
        return 1.0, 1.0

def calcular_il(razao_preco):
    if razao_preco <= 0:
        return 0.0
    il = (2 * math.sqrt(razao_preco) / (1 + razao_preco)) - 1
    return il * 100

# -----------------------------------------------------------------------------
# 4. BARRA LATERAL & OPÇÕES
# -----------------------------------------------------------------------------
pools = get_pools()

st.sidebar.title("⚡ DeFi Hub Pro")
filtro_estado = st.sidebar.selectbox("Filtrar Posições:", ["Apenas Abertas (Ativas/Fora)", "Ativas 🟢", "Fora de Range 🔴", "Fechadas 📁", "Todas"])

esconder_detalhes = st.sidebar.checkbox("👁️ Ocultar Detalhes das Pools", value=False)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Sincronizar Tudo", use_container_width=True):
    with st.spinner("A atualizar posições abertas..."):
        agora = time.time()
        for p in pools:
            estado_norm = normalizar_estado(p.get("estado"))
            
            # BLOQUEIO DEFINITIVO: Posições Fechadas nunca são alteradas pela sincronização
            if estado_norm == "Fechada":
                continue
                
            addr = p.get("wallet_address")
            par = p.get("par", "Par N/A")
            if addr:
                p_usd, p_nat = fetch_dexscreener_data(addr)
                if p_nat is not None:
                    r_min = to_float(p.get("range_min"))
                    r_max = to_float(p.get("range_max"))
                    
                    in_range = True
                    desvio_txt = ""
                    if r_max > 0 and p_nat > r_max:
                        in_range = False
                        pct = ((p_nat - r_max) / r_max) * 100
                        desvio_txt = f"+{pct:.2f}% máx"
                    elif r_min > 0 and p_nat < r_min:
                        in_range = False
                        pct = ((r_min - p_nat) / r_min) * 100
                        desvio_txt = f"-{pct:.2f}% mín"
                    
                    novo_estado = "Ativa" if in_range else "Inativa"
                    estado_anterior = estado_norm
                    last_update = to_float(p.get("last_price_update"))
                    horas_inativas_atuais = to_float(p.get("horas_inativa"))
                    
                    if novo_estado == "Inativa":
                        if estado_anterior == "Inativa" and last_update > 0:
                            horas_decorridas = (agora - last_update) / 3600.0
                            novas_horas_inativa = horas_inativas_atuais + horas_decorridas
                        else:
                            novas_horas_inativa = horas_inativas_atuais
                    else:
                        novas_horas_inativa = horas_inativas_atuais
                    
                    patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{p['id']}"
                    patch_data = {
                        "preco_nativo": p_nat,
                        "estado": novo_estado,
                        "horas_inativa": novas_horas_inativa,
                        "last_price_update": agora
                    }
                    if p_usd:
                        patch_data["preco_atual"] = p_usd
