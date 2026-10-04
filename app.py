import streamlit as st
import pandas as pd
import requests
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURAÇÃO E CONEXÃO
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
# 2. CARREGAR E GUARDAR DADOS
# ==========================================
def carregar_pools():
    try:
        response = supabase.table("pools").select("*").order("id").execute()
        return response.data or []
    except Exception as e:
        st.error(f"Erro ao ligar ao Supabase: {e}")
        return []

def guardar_ou_atualizar_pool(dados_pool):
    try:
        if "id" in dados_pool and dados_pool["id"]:
            pool_id = dados_pool.pop("id")
            supabase.table("pools").update(dados_pool).eq("id", pool_id).execute()
        else:
            if "id" in dados_pool:
                dados_pool.pop("id")
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
# 3. ALERTAS DO TELEGRAM
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
                enviar_alerta_telegram(f"⚠️ *ALERTA (ABAIXO):* {par}\nPreço Actual: `${preco_atual}` | Mín: `${range_min}`")
            elif preco_atual > range_max:
                enviar_alerta_telegram(f"⚠️ *ALERTA (ACIMA):* {par}\nPreço Actual: `${preco_atual}` | Máx: `${range_max}`")
        except Exception:
            continue

# ==========================================
# 4. PAINEL PRINCIPAL
# ==========================================
st.title("⚡ Gestor de Piscinas de Liquidez")

pools_data = carregar_pools()

# METRICAS
st.subheader("📌 Resumo Executivo")
total_liquidez = sum([float(p.get("valor_atual", 0) or 0) for p in pools_data])
total_fees = sum([float(p.get("fees", 0) or 0) for p in pools_data])
apr_medio = (total_fees / total_liquidez * 100) if total_liquidez > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
col2.metric("Total Fees Acumuladas", f"${total_fees:,.2f}")
col3.metric("APR Médio das Fees", f"{apr_medio:.2f}%")

st.divider()

# SIDEBAR FORM
with st.sidebar:
    st.header("➕ Adicionar / Editar Piscina")
    
    # Seleção para editar linha existente
    opcoes_pools = {"Nova Piscina": None}
    for p in pools_data:
        opcoes_pools[f"ID {p.get('id')} - {p.get('par')} ({p.get('rede')})"] = p
        
    selecao = st.selectbox("Escolher acção:", list(opcoes_pools.keys()))
    pool_seleccionada = opcoes_pools[selecao]
    
    with st.form("form_pool"):
        id_val = pool_seleccionada.get("id") if pool_seleccionada else None
        par_val = pool_seleccionada.get("par", "SOL/PUMP") if pool_seleccionada else "SOL/PUMP"
        rede_val = pool_seleccionada.get("rede", "SOLANA") if pool_seleccionada else "SOLANA"
        wallet_val = pool_seleccionada.get("wallet_address", "") if pool_seleccionada else ""
        v_ini_val = float(pool_seleccionada.get("valor_inicial", 0) or 0) if pool_seleccionada else 0.0
        v_act_val = float(pool_seleccionada.get("valor_atual", 0) or 0) if pool_seleccionada else 0.0
        r_min_val = float(pool_seleccionada.get("range_min", 0) or 0) if pool_seleccionada else 0.0
        r_max_val = float(pool_seleccionada.get("range_max", 0) or 0) if pool_seleccionada else 0.0
        fees_val = float(pool_seleccionada.get("fees", 0) or 0) if pool_seleccionada else 0.0
        estado_val = pool_seleccionada.get("estado", "Ativa") if pool_seleccionada else "Ativa"

        par = st.text_input("Par de Tokens", value=par_val)
        rede = st.text_input("Rede / DEX", value=rede_val)
        wallet_address = st.text_input("Morada do Par / Pair Address", value=wallet_val)
        valor_inicial = st.number_input("Valor Inicial ($)", min_value=0.0, value=v_ini_val, step=10.0)
        valor_atual = st.number_input("Valor Actual ($)", min_value=0.0, value=v_act_val, step=10.0)
        range_min = st.number_input("Range Mínimo", min_value=0.0, value=r_min_val, format="%.6f")
        range_max = st.number_input("Range Máximo", min_value=0.0, value=r_max_val, format="%.6f")
        fees = st.number_input("Fees Acumuladas ($)", min_value=0.0, value=fees_val, step=1.0)
        
        lista_estados = ["Ativa", "Inativa", "Fechada"]
        idx_estado = lista_estados.index(estado_val) if estado_val in lista_estados else 0
        estado = st.selectbox("Estado", lista_estados, index=idx_estado)
        
        submitted = st.form_submit_button("💾 Sincronizar e Guardar")
        if submitted:
            preco_live = obter_preco_dexscreener(wallet_address)
            dados_para_guardar = {
                "par": par,
                "rede": rede,
                "wallet_address": wallet_address,
                "valor_inicial": valor_inicial,
                "valor_atual": valor_atual,
                "range_min": range_min,
                "range_max": range_max,
                "fees": fees,
                "estado": estado,
                "preco_atual": preco_live if preco_live > 0 else (pool_seleccionada.get("preco_atual", 0) if pool_seleccionada else 0)
            }
            if id_val:
                dados_para_guardar["id"] = id_val
                
            if guardar_ou_atualizar_pool(dados_para_guardar):
                st.success("Operação concluída com sucesso!")
                st.rerun()

# MOSTRAR TABELA
st.subheader("📋 Suas Piscinas")

if pools_data:
    df = pd.DataFrame(pools_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    verificar_ranges_e_alertar(pools_data)
else:
    st.warning("Nenhum dado retornado pelo Supabase.")
