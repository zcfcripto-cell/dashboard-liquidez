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

# Inicializar cliente do Supabase
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# ==========================================
# 2. FUNÇÕES DO TELEGRAM E ALERTAS
# ==========================================
def enviar_alerta_telegram(mensagem: str):
    """Envia uma notificação direta para o Telegram do utilizador."""
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            st.error(f"Erro ao enviar alerta para o Telegram: {e}")

def verificar_ranges_e_alertar(pools_list):
    """Verifica se alguma piscina está fora do range e dispara alertas."""
    for pool in pools_list:
        par = pool.get("par", "Desconhecido")
        preco_atual = float(pool.get("preco_atual", 0))
        range_min = float(pool.get("range_min", 0))
        range_max = float(pool.get("range_max", 0))
        estado = pool.get("estado", "Ativa")
        
        # Só verifica se estiver ativa e tiver ranges configurados
        if estado != "Ativa" or (range_min == 0 and range_max == 0):
            continue
            
        if preco_atual < range_min:
            msg = (
                f"⚠️ *ALERTA DE RANGE (ABAIXO)* ⚠️\n\n"
                f"📌 *Par:* {par}\n"
                f"📉 *Preço Atual:* `${preco_atual:.6f}`\n"
                f"🔻 *Mínimo Definido:* `${range_min:.6f}`\n\n"
                f"⚡ *Ação:* O preço caiu abaixo da tua zona de liquidez!"
            )
            enviar_alerta_telegram(msg)
            
        elif preco_atual > range_max:
            msg = (
                f"⚠️ *ALERTA DE RANGE (ACIMA)* ⚠️\n\n"
                f"📌 *Par:* {par}\n"
                f"📈 *Preço Atual:* `${preco_atual:.6f}`\n"
                f"🔺 *Máximo Definido:* `${range_max:.6f}`\n\n"
                f"⚡ *Ação:* O preço subiu acima da tua zona de liquidez!"
            )
            enviar_alerta_telegram(msg)

# ==========================================
# 3. OPERAÇÕES DE BASE DE DADOS (SUPABASE)
# ==========================================
def carregar_pools():
    """Carrega todas as piscinas registadas no Supabase."""
    try:
        response = supabase.table("pools").select("*").execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao carregar piscinas do Supabase: {e}")
        return []

def guardar_ou_atualizar_pool(dados_pool):
    """Guarda uma nova piscina ou atualiza uma existente."""
    try:
        if "id" in dados_pool and dados_pool["id"]:
            supabase.table("pools").update(dados_pool).eq("id", dados_pool["id"]).execute()
        else:
            supabase.table("pools").insert(dados_pool).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao guardar no Supabase: {e}")
        return False

# ==========================================
# 4. CONSULTA DE PREÇOS (DEXSCREENER)
# ==========================================
def obter_preco_dexscreener(pair_address):
    """Obtém o preço atual de um par através da API do DexScreener."""
    if not pair_address:
        return 0.0
    try:
        url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
        res = requests.get(url, timeout=5).json()
        if res.get("pairs"):
            return float(res["pairs"][0].get("priceUsd", 0.0))
    except Exception:
        pass
    return 0.0

# ==========================================
# 5. INTERFACE DO UTILIZADOR (STREAMLIT)
# ==========================================
st.title("⚡ Gestor de Piscinas de Liquidez")
st.caption("Acompanhamento de performance e gestão DeFi (Persistência Cloud Activa)")

# Carregar dados atuais
pools_data = carregar_pools()

# --- RESUMO EXECUTIVO ---
st.subheader("📌 Resumo Executivo")

total_liquidez = sum([float(p.get("valor_atual", 0)) for p in pools_data])
total_fees = sum([float(p.get("fees", 0)) for p in pools_data])
apr_medio = (total_fees / total_liquidez * 100) if total_liquidez > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
col2.metric("Total Fees Acumuladas", f"${total_fees:,.2f}")
col3.metric("APR Médio das Fees", f"{apr_medio:.2f}%")

st.divider()

# --- FORMULÁRIO DE REGISTO / ATUALIZAÇÃO ---
with st.sidebar:
    st.header("➕ Gerir Piscina")
    
    with st.form("form_pool"):
        par = st.text_input("Par de Tokens (ex: SOL/PUMP)", value="SOL/PUMP")
        rede = st.selectbox("Rede", ["SOLANA", "ETHEREUM", "BASE", "ARBITRUM"])
        wallet_address = st.text_input("Morada da Wallet / Pair Address")
        
        c_val1, c_val2 = st.columns(2)
        valor_inicial = c_val1.number_input("Valor Inicial ($)", min_value=0.0, step=10.0)
        valor_atual = c_val2.number_input("Valor Atual ($)", min_value=0.0, step=10.0)
        
        c_range1, c_range2 = st.columns(2)
        range_min = c_range1.number_input("Range Mínimo ($)", min_value=0.0, format="%.6f")
        range_max = c_range2.number_input("Range Máximo ($)", min_value=0.0, format="%.6f")
        
        fees = st.number_input("Fees Acumuladas ($)", min_value=0.0, step=1.0)
        estado = st.selectbox("Estado", ["Ativa", "Inativa", "Fechada"])
        
        submitted = st.form_submit_button("💾 Sincronizar e Guardar")
        
        if submitted:
            # Tentar obter o preço atual antes de guardar
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
                st.success("Piscina guardada com sucesso!")
                st.rerun()

    # Botão manual para testar envio do Telegram
    if st.button("📲 Testar Alerta Telegram"):
        enviar_alerta_telegram("🚀 *Teste de Conexão:* O teu Gestor DeFi está ligado com sucesso ao Telegram!")
        st.toast("Mensagem de teste enviada!")

# --- TABELA DE POOLS REGISTADAS ---
st.subheader("📋 Suas Piscinas Ativas")

if pools_data:
    df = pd.DataFrame(pools_data)
    
    # Selecionar e renomear colunas para apresentação limpa
    colunas_exibir = ["par", "rede", "valor_atual", "fees", "range_min", "range_max", "preco_atual", "estado"]
    colunas_presentes = [c for c in colunas_exibir if c in df.columns]
    
    st.dataframe(
        df[colunas_presentes],
        use_container_width=True,
        hide_index=True
    )
    
    # Executar verificação de limites/ranges
    verificar_ranges_e_alertar(pools_data)
else:
    st.info("Nenhuma piscina registada.")
