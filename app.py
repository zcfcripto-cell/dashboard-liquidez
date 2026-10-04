import streamlit as st
import pandas as pd
import requests
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURAÇÃO INICIAL E CONEXÕES
# ==========================================
st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    page_icon="⚡",
    layout="wide"
)

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# ==========================================
# 2. TELEGRAM E ALERTAS (ISOLADO)
# ==========================================
def enviar_alerta_telegram(mensagem: str):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

def verificar_ranges_e_alertar(pools_list):
    for pool in pools_list:
        try:
            par = pool.get("par", "Desconhecido")
            preco_atual = float(pool.get("preco_atual", 0) or 0)
            range_min = float(pool.get("range_min", 0) or 0)
            range_max = float(pool.get("range_max", 0) or 0)
            estado = pool.get("estado", "Ativa")
            
            if estado != "Ativa" or (range_min == 0 and range_max == 0) or preco_atual == 0:
                continue
                
            if preco_atual < range_min:
                enviar_alerta_telegram(f"⚠️ *ALERTA (ABAIXO):* {par}\nPreço: `${preco_atual}` | Mín: `${range_min}`")
            elif preco_atual > range_max:
                enviar_alerta_telegram(f"⚠️ *ALERTA (ACIMA):* {par}\nPreço: `${preco_atual}` | Máx: `${range_max}`")
        except Exception:
            continue

# ==========================================
# 3. BASE DE DADOS & PREÇOS
# ==========================================
def carregar_pools():
    try:
        response = supabase.table("pools").select("*").execute()
        return response.data or []
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return []

def guardar_ou_atualizar_pool(dados_pool):
    try:
        supabase.table("pools").insert(dados_pool).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao guardar no Supabase: {e}")
        return False

def obter_preco_dexscreener(pair_address):
    if not pair_address or len(str(pair_address).strip()) < 10:
        return 0.0
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={pair_address.strip()}"
        res = requests.get(url, timeout=5).json()
        if res.get("pairs") and len(res["pairs"]) > 0:
            return float(res["pairs"][0].get("priceUsd", 0.0))
    except Exception:
        pass
    return 0.0

# ==========================================
# 4. INTERFACE PRINCIPAL
# ==========================================
st.title("⚡ Gestor de Piscinas de Liquidez")
st.caption("Acompanhamento de performance e gestão DeFi")

pools_data = carregar_pools()

# RESUMO EXECUTIVO
st.subheader("📌 Resumo Executivo")
total_liquidez = sum([float(p.get("valor_atual", 0) or 0) for p in pools_data])
total_fees = sum([float(p.get("fees", 0) or 0) for p in pools_data])
apr_medio = (total_fees / total_liquidez * 100) if total_liquidez > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
col2.metric("Total Fees Acumuladas", f"${total_fees:,.2f}")
col3.metric("APR Médio das Fees", f"{apr_medio:.2f}%")

st.divider()

# PAINEL LATERAL
with st.sidebar:
    st.header("➕ Gerir Piscina")
    with st.form("form_pool"):
        par = st.text_input("Par de Tokens", value="SOL/PUMP")
        rede = st.selectbox("Rede", ["SOLANA", "ETHEREUM", "BASE", "ARBITRUM"])
        wallet_address = st.text_input("Morada do Par / Pair Address")
        valor_inicial = st.number_input("Valor Inicial ($)", min_value=0.0, step=10.0)
        valor_atual = st.number_input("Valor Atual ($)", min_value=0.0, step=10.0)
        range_min = st.number_input("Range Mínimo ($)", min_value=0.0, format="%.6f")
        range_max = st.number_input("Range Máximo ($)", min_value=0.0, format="%.6f")
        fees = st.number_input("Fees Acumuladas ($)", min_value=0.0, step=1.0)
        estado = st.selectbox("Estado", ["Ativa", "Inativa", "Fechada"])
        
        submitted = st.form_submit_button("💾 Sincronizar e Guardar")
        if submitted:
            preco_live = obter_preco_dexscreener(wallet_address)
            nova_pool = {
                "par": par,
                "rede": rede,
                "wallet_address": wallet_address,
                "valor_inicial": valor_inicial,
                "valor_atual": valor_atual,
                "range_min": range_min,
                "range_max": range_max,
                "fees": fees,
                "estado": estado,
                "preco_atual": preco_live
            }
            if guardar_ou_atualizar_pool(nova_pool):
                st.success("Piscina guardada!")
                st.rerun()

# TABELA DE POOLS - APRESENTAÇÃO DIRETA
st.subheader("📋 Suas Piscinas Ativas")

if pools_data:
    df = pd.DataFrame(pools_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    verificar_ranges_e_alertar(pools_data)
else:
    st.info("Nenhuma piscina encontrada na base de dados.")
