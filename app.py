import os
import time
import math
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
    .pool-card-closed { border-left: 5px solid #6b7280; opacity: 0.75; }
    
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

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -----------------------------------------------------------------------------
# 3. FUNÇÕES AUXILIARES & SPARKLINE
# -----------------------------------------------------------------------------
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

def render_sparkline_chart(preco_atual, range_min, range_max):
    if preco_atual <= 0:
        return
    
    steps = 15
    import numpy as np
    x_vals = list(range(steps))
    variacao = np.linspace(-0.04, 0, steps) + np.random.normal(0, 0.01, steps)
    y_vals = [preco_atual * (1 + v) for v in variacao]
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
# 4. BARRA LATERAL & SINCRONIZAÇÃO
# -----------------------------------------------------------------------------
pools = get_pools()

st.sidebar.title("⚡ DeFi Hub Pro")
filtro_estado = st.sidebar.selectbox("Filtrar Posições:", ["Apenas Abertas (Ativas/Fora)", "Ativas 🟢", "Fora de Range 🔴", "Fechadas 📁", "Todas"])

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Sincronizar Tudo", use_container_width=True):
    with st.spinner("A atualizar posições abertas..."):
        agora = time.time()
        for p in pools:
            # TRAVA DE SEGURANÇA: Ignorar estritamente pools fechadas na sincronização
            if str(p.get("estado", "")).strip().lower() in ["fechada", "closed"]:
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
                    estado_anterior = p.get("estado", "Ativa")
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
                        
                    requests.patch(patch_url, headers=headers, json=patch_data)

                    if novo_estado == "Inativa" and estado_anterior == "Ativa":
                        send_telegram(f"🚨 <b>FORA DE RANGE:</b> {par}\nPreço: {format_crypto_price(p_nat)}\nDesvio: {desvio_txt}")
                    elif novo_estado == "Ativa" and estado_anterior == "Inativa":
                        send_telegram(f"🟢 <b>VOLTOU AO RANGE:</b> {par}\nPreço: {format_crypto_price(p_nat)}")

    st.sidebar.success("Sincronizado!")
    st.rerun()

# -----------------------------------------------------------------------------
# 5. CÁLCULO DE MÉTRICAS COMPLETO
# -----------------------------------------------------------------------------
total_investido = 0.0
total_valor_atual = 0.0
total_fees = 0.0
total_fees_diarias_corridas = 0.0
total_fees_diarias_ativas = 0.0
total_ativas = 0
total_inativas = 0
total_fechadas = 0

pools_processadas = []

for p in pools:
    v_inv = to_float(p.get("valor_inicial"))
    v_at = to_float(p.get("valor_atual"))
    v_fees = to_float(p.get("fees"))
    data_ent = p.get("data_entrada", "")
    hrs_inativa = to_float(p.get("horas_inativa"))
    estado = p.get("estado", "Ativa")

    v_atual_final = v_at if v_at > 0 else v_inv
    pnl_pool = (v_atual_final + v_fees) - v_inv
    roi_pool = (pnl_pool / v_inv * 100) if v_inv > 0 else 0.0

    dias_corridos, dias_ativos = calcular_dias_metricas(data_ent, hrs_inativa)
    
    fees_dia_corrido = v_fees / dias_corridos
    apr_corrido = ((v_fees / v_inv) / dias_corridos * 365 * 100) if v_inv > 0 else 0.0

    fees_dia_ativo = v_fees / dias_ativos
