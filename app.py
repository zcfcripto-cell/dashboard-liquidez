import datetime
import json
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------
# CONEXÃO COM SUPABASE VIA REST API (PERSISTÊNCIA NA NUVEM)
# -------------------------------------------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def load_pools():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.warning("Configura os Secrets (SUPABASE_URL e SUPABASE_KEY) para ativar a persistência na nuvem.")
        return []

    url = f"{SUPABASE_URL}/rest/v1/pools?select=*"
    try:
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            data = res.json()
            pools = []
            for r in data:
                try:
                    dt_ent = datetime.datetime.strptime(str(r.get("data_entrada")), "%Y-%m-%d").date()
                except Exception:
                    dt_ent = datetime.date.today()

                pools.append({
                    "id": int(r.get("id")),
                    "par": str(r.get("par", "POOL/USD")),
                    "rede": str(r.get("rede", "DEX")),
                    "estado": str(r.get("estado", "Ativa")),
                    "valor_inicial": float(r.get("valor_inicial", 0)),
                    "valor_atual": float(r.get("valor_atual", 0)),
                    "fees": float(r.get("fees", 0)),
                    "range_min": float(r.get("range_min", 0)),
                    "range_max": float(r.get("range_max", 0)),
                    "data_entrada": dt_ent,
                    "wallet_address": str(r.get("wallet_address", ""))
                })
            return sorted(pools, key=lambda x: x["id"])
    except Exception as e:
        st.error(f"Erro ao carregar piscinas: {e}")
    return []

def add_pool_db(par, rede, valor_inicial, valor_atual, fees, r_min, r_max, data_in, wallet_addr):
    url = f"{SUPABASE_URL}/rest/v1/pools"
    payload = {
        "par": par,
        "rede": rede,
        "estado": "Ativa",
        "valor_inicial": valor_inicial,
        "valor_atual": valor_atual,
        "fees": fees,
        "range_min": r_min,
        "range_max": r_max,
        "data_entrada": data_in.strftime("%Y-%m-%d"),
        "wallet_address": wallet_addr
    }
    requests.post(url, headers=HEADERS, json=payload)

def update_pool_db(pool_id, valor_atual, fees, data_entrada, wallet_addr="", r_min=None, r_max=None):
    url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
    payload = {
        "valor_atual": valor_atual,
        "fees": fees,
        "data_entrada": data_entrada.strftime("%Y-%m-%d"),
        "wallet_address": wallet_addr
    }
    if r_min is not None and r_max is not None:
        payload["range_min"] = r_min
        payload["range_max"] = r_max
    requests.patch(url, headers=HEADERS, json=payload)

def delete_pool_db(pool_id):
    url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
    requests.delete(url, headers=HEADERS)

# -------------------------------------------------------------
# CONSULTA DE PREÇOS NO DEXSCREENER
# -------------------------------------------------------------
def fetch_dexscreener_price(position_nft_address):
    if not position_nft_address or not isinstance(position_nft_address, str):
        return None, None
    clean_addr = position_nft_address.strip()
    if not clean_addr:
        return None, None
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{clean_addr}"
    try:
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data and "pair" in data and data["pair"]:
                price_usd = float(data["pair"].get("priceUsd", 0))
                price_native = float(data["pair"].get("priceNative", 0))
                return price_usd, price_native
    except Exception:
        pass
    return None, None

# ESTILOS CSS
st.markdown("""
    <style>
    .stApp {
        background-color: #0b0e14;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .info-box {
        background-color: #11161d;
        border: 1px solid #1f242c;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 13px;
        color: #9ca3af;
    }
    .info-box strong { color: #f3f4f6; }
    .badge-ativa {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
    }
    .badge-fechada {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
    }
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
    }
    </style>
""", unsafe_allow_html=True)

# HEADER
st.title("⚡ Gestor de Piscinas de Liquidez")
st.caption("Acompanhamento de performance com persistência Cloud")

pools_data = load_pools()

DEX_OPTIONS = ["Raydium", "Uniswap v3", "Orca", "Kamino", "PancakeSwap", "Curve", "Meteora", "Cetus", "Outro"]

# PAINEL LATERAL
with st.sidebar:
    st.header("➕ Nova Pool")
    with st.form("nova_pool_form", clear_on_submit=True):
        par = st.text_input("Par (ex: SOL/PUMP)")
        rede = st.text_input("Rede / Plataforma")
        dex = st.selectbox("DEX", DEX_OPTIONS)
        v_init = st.number_input("Valor Inicial ($)", min_value=0.0)
        v_atual = st.number_input("Valor Atual ($)", min_value=0.0)
        fees_in = st.number_input("Fees Pendentes ($)", min_value=0.0)
        wallet_addr = st.text_input("Position Address")
        col_r1, col_r2 = st.columns(2)
        r_min = col_r1.number_input("Range Mín", format="%.6f", step=0.000001)
        r_max = col_r2.number_input("Range Máx", format="%.6f", step=0.000001)
        data_in = st.date_input("Data Entrada", datetime.date.today())

        if st.form_submit_button("Adicionar Pool", type="primary"):
            nome_par = par if par else "POOL/USD"
            nome_rede = f"{dex} - {rede if rede else 'Rede'}"
            v_actual_calc = v_atual if v_atual > 0 else v_init
            add_pool_db(nome_par, nome_rede, float(v_init), float(v_actual_calc), float(fees_in), float(r_min), float(r_max), data_in, wallet_addr)
            st.success("Pool gravada na Nuvem!")
            st.rerun()

# RESUMO EXECUTIVO
total_liquidez = sum(p["valor_atual"] for p in pools_data)
total_fees = sum(p["fees"] for p in pools_data)

dt_hoje = datetime.date.today()
aprs_com_peso = []
pesos_iniciais = []

for p in pools_data:
    dt_ent = p.get("data_entrada", dt_hoje)
    dias = max(1, (dt_hoje - dt_ent).days)
    if p["valor_inicial"] > 0:
        apr_p = (p["fees"] / p["valor_inicial"]) * (365 / dias) * 100
        aprs_com_peso.append(apr_p * p["valor_inicial"])
        pesos_iniciais.append(p["valor_inicial"])

total_v_init = sum(pesos_iniciais)
media_apr_fees = sum(aprs_com_peso) / total_v_init if total_v_init > 0 else 0.0

st.markdown("### 📌 Resumo Executivo")
c1, c2, c3 = st.columns(3)
c1.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
c2.metric("Total Fees Acumuladas", f"${total_fees:,.2f}")
c3.metric("APR Médio das Fees", f"{media_apr_fees:.2f}%")

st.markdown("---")

if not pools_data:
    st.info("Nenhuma piscina registada.")
else:
    for idx, pool in enumerate(pools_data, start=1):
        dt_entrada = pool.get("data_entrada", datetime.date.today())
        dias_totais = max(1, (dt_hoje - dt_entrada).days)

        pnl = (pool["valor_atual"] + pool["fees"]) - pool["valor_inicial"]
        variacao_pct = ((pool["valor_atual"] - pool["valor_inicial"]) / pool["valor_inicial"]) * 100 if pool["valor_inicial"] > 0 else 0
        apr_total = (pool["fees"] / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0

        with st.container():
            head_col1, head_col2 = st.columns([2, 3])
            with head_col1:
                badge_class = "badge-ativa" if pool["estado"] == "Ativa" else "badge-fechada"
                st.markdown(f"### 🪙 **Pool #{idx}: {pool['par']}** <span class='{badge_class}'>{pool['estado']}</span>", unsafe_allow_html=True)
                st.caption(f"DEX / Rede: {pool['rede']}")

            with head_col2:
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Valor Atual", f"${pool['valor_atual']:,.2f}")
                m2.metric("Variação", f"{variacao_pct:+.2f}%")
                m3.metric("PnL Total", f"${pnl:+.2f}")
                m4.metric("APR Total", f"{apr_total:.2f}%")
                m5.metric("Fees", f"${pool['fees']:,.2f}")

            st.markdown("---")
