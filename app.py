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
# 2. FUNÇÕES DE SUPORTE (API DEXSCREENER & SUPABASE)
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
    except Exception as e:
        st.error(f"Erro ao consultar DexScreener: {e}")
    return None, None

def get_pools():
    """Lê todas as pools da base de dados Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/pools?select=*&order=id.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Erro ao carregar pools: {e}")
    return []

def get_historico_pnl():
    """Lê a tabela historico_pnl para desenhar os gráficos."""
    url = f"{SUPABASE_URL}/rest/v1/historico_pnl?select=*&order=data.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def to_float(val, default=0.0):
    """Converte valores com segurança para float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# -----------------------------------------------------------------------------
# 3. INTERFACE PRINCIPAL & CABEÇALHO
# -----------------------------------------------------------------------------
st.title("⚡ Gestor de Piscinas de Liquidez (DeFi Dashboard)")

pools = get_pools()

# Processamento e conversão de dados das pools
total_investido = 0.0
total_valor_atual = 0.0

for p in pools:
    v_inv = to_float(p.get("valor_investido"))
    qtd = to_float(p.get("quantidade"))
    p_usd = to_float(p.get("preco_atual"))
    
    total_investido += v_inv
    
    if qtd > 0 and p_usd > 0:
        total_valor_atual += (qtd * p_usd)
    else:
        total_valor_atual += v_inv

pnl_global = total_valor_atual - total_investido
roi_global = (pnl_global / total_investido * 100) if total_investido > 0 else 0.0

# Exibição dos Cartões Principais
col1, col2, col3, col4 = st.columns(4)
col1.metric("Investimento Total", f"${total_investido:,.2f}")
col2.metric("Valor Atual Estimado", f"${total_valor_atual:,.2f}")
col3.metric("PnL Total ($)", f"${pnl_global:,.2f}", delta=f"${pnl_global:,.2f}")
col4.metric("ROI Acumulado (%)", f"{roi_global:.2f}%", delta=f"{roi_global:.2f}%")

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. BOTÃO DE SINCRONIZAÇÃO
# -----------------------------------------------------------------------------
col_sync, _ = st.columns([1, 3])
with col_sync:
    if st.button("🔗 Sincronizar Preços Agora", use_container_width=True):
        with st.spinner("A atualizar preços e estados das pools..."):
            for p in pools:
                addr = p.get("wallet_address")
                if addr:
                    p_usd, p_nat = fetch_dexscreener_data(addr)
                    if p_nat is not None:
                        r_min = to_float(p.get("range_min"))
                        r_max = to_float(p.get("range_max"))
                        
                        in_range = True
                        if r_min > 0 and p_nat < r_min:
                            in_range = False
                        elif r_max > 0 and p_nat > r_max:
                            in_range = False
                        
                        novo_estado = "Ativa" if in_range else "Inativa"
                        
                        patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{p['id']}"
                        patch_data = {
                            "preco_atual": p_usd,
                            "preco_nativo": p_nat,
                            "estado": novo_estado,
                            "last_price_update": time.time()
                        }
                        requests.patch(patch_url, headers=headers, json=patch_data)
        st.success("Sincronização concluída!")
        st.rerun()

# -----------------------------------------------------------------------------
# 5. TABELA DE POOLS & GESTÃO (CRUD)
# -----------------------------------------------------------------------------
st.subheader("📋 Minhas Piscinas de Liquidez")

if pools:
    df_pools = pd.DataFrame(pools)
    cols_display = ["id", "par", "estado", "preco_nativo", "range_min", "range_max", "valor_investido", "quantidade", "wallet_address"]
    cols_existentes = [c for c in cols_display if c in df_pools.columns]
    
    st.dataframe(
        df_pools[cols_existentes],
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Nenhuma piscina registada até ao momento.")

# Formulário para Adicionar Nova Pool
with st.expander("➕ Adicionar Piscina"):
    with st.form("form_pool"):
        c1, c2, c3 = st.columns(3)
        par_input = c1.text_input("Par (ex: PUMP/SOL)", "")
        addr_input = c2.text_input("Pair Address (DexScreener)", "")
        invest_input = c3.number_input("Valor Investido ($ USD)", min_value=0.0, step=10.0)
        
        c4, c5, c6 = st.columns(3)
        rmin_input = c4.number_input("Range Mínimo (Preço Nativo)", min_value=0.0, format="%.8f")
        rmax_input = c5.number_input("Range Máximo (Preço Nativo)", min_value=0.0, format="%.8f")
        qtd_input = c6.number_input("Quantidade de Tokens", min_value=0.0, step=0.1)

        btn_salvar = st.form_submit_button("Guardar Piscina")

        if btn_salvar:
            if not par_input or not addr_input:
                st.warning("Preencha o nome do par e a morada (Pair Address).")
            else:
                p_usd, p_nat = fetch_dexscreener_data(addr_input)
                payload = {
                    "par": par_input,
                    "wallet_address": addr_input,
                    "valor_investido": invest_input,
                    "range_min": rmin_input,
                    "range_max": rmax_input,
                    "quantidade": qtd_input,
                    "preco_atual": p_usd or 0,
                    "preco_nativo": p_nat or 0,
                    "estado": "Ativa"
                }
                res = requests.post(f"{SUPABASE_URL}/rest/v1/pools", headers=headers, json=payload)
                if res.status_code in [200, 201]:
                    st.success("Piscina guardada com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao guardar: {res.text}")

# -----------------------------------------------------------------------------
# 6. HISTÓRICO DE EVOLUÇÃO DE PNL & CARTEIRA (MELHORIA #2)
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📈 Evolução Histórica de Valor e PnL")

hist_data = get_historico_pnl()

if hist_data:
    df_hist = pd.DataFrame(hist_data)
    
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        fig_valor = px.line(
            df_hist, 
            x="data", 
            y="valor_total_usd", 
            title="Evolução do Valor Total da Carteira ($ USD)",
            markers=True
        )
        fig_valor.update_traces(line_color="#00CC96", line_width=3)
        st.plotly_chart(fig_valor, use_container_width=True)
        
    with col_g2:
        fig_pnl = px.bar(
            df_hist, 
            x="data", 
            y="pnl_usd", 
            title="Lucro / Prejuízo Acumulado ($ USD)",
            color="pnl_usd",
            color_continuous_scale=["#FF2B2B", "#00CC96"]
        )
        st.plotly_chart(fig_pnl, use_container_width=True)
else:
    st.info("💡 O histórico de PnL começará a desenhar gráficos assim que o GitHub Action executar a verificação diária ou quando sincronizar os dados.")
