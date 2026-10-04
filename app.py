import os
import time
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA & ESTILOS CSS CUSTOM
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="DeFi Liquidity Hub Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo Personalizado Profissional (Dark Theme CSS)
st.markdown("""
<style>
    /* Estilização Geral e Fundos */
    .stApp {
        background-color: #0e1117;
    }
    
    /* Cartões de Métricas */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    
    /* Cards Customizados para Pools */
    .pool-card {
        background-color: #1a1f2c;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #2d3748;
        margin-bottom: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .pool-card-active {
        border-left: 5px solid #10b981;
    }
    .pool-card-inactive {
        border-left: 5px solid #ef4444;
    }
    
    /* Badges de Estado */
    .badge-active {
        background-color: rgba(16, 185, 129, 0.2);
        color: #10b981;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-inactive {
        background-color: rgba(239, 68, 68, 0.2);
        color: #ef4444;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. CREDENCIAIS & LIGAÇÃO AO SUPABASE
# -----------------------------------------------------------------------------
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
# 3. FUNÇÕES AUXILIARES E API DEXSCREENER
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
        st.error(f"Erro no DexScreener: {e}")
    return None, None

def get_pools():
    """Lê todas as pools registadas no Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/pools?select=*&order=id.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Erro ao carregar pools: {e}")
    return []

def get_historico_pnl():
    """Lê o histórico diário de PnL para os gráficos."""
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

# -----------------------------------------------------------------------------
# 4. CARREGAMENTO DE DADOS & BARRA LATERAL (FILTROS)
# -----------------------------------------------------------------------------
pools = get_pools()

st.sidebar.image("https://img.icons8.com/isometric-line/100/10B981/cryptocurrency.png", width=60)
st.sidebar.title("DeFi Hub Pro")
st.sidebar.caption("Monitorização em tempo real & Alertas Telegram")

# Filtro de Estado
filtro_estado = st.sidebar.selectbox("Filtrar Posições:", ["Todas", "Ativas 🟢", "Fora de Range 🔴"])

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Sincronizar Tudo Agora", use_container_width=True):
    with st.spinner("A consultar DexScreener..."):
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
    st.sidebar.success("Atualizado!")
    st.rerun()

st.sidebar.info("💡 **Alertas Automáticos:** O teu GitHub Action envia notificações diretas para o Telegram se alguma pool sair da amplitude configurada.")

# -----------------------------------------------------------------------------
# 5. CÁLCULO DAS MÉTRICAS GERAIS DO PORTFÓLIO
# -----------------------------------------------------------------------------
total_investido = 0.0
total_valor_atual = 0.0
total_ativas = 0
total_inativas = 0

pools_processadas = []

for p in pools:
    v_inv = to_float(p.get("valor_investido"))
    qtd = to_float(p.get("quantidade"))
    p_usd = to_float(p.get("preco_atual"))
    p_nat = to_float(p.get("preco_nativo"))
    r_min = to_float(p.get("range_min"))
    r_max = to_float(p.get("range_max"))
    estado = p.get("estado", "Ativa")

    v_atual = (qtd * p_usd) if (qtd > 0 and p_usd > 0) else v_inv
    pnl_pool = v_atual - v_inv
    roi_pool = (pnl_pool / v_inv * 100) if v_inv > 0 else 0.0

    total_investido += v_inv
    total_valor_atual += v_atual

    if estado == "Ativa":
        total_ativas += 1
    else:
        total_inativas += 1

    p_item = p.copy()
    p_item["v_atual"] = v_atual
    p_item["pnl_pool"] = pnl_pool
    p_item["roi_pool"] = roi_pool
    pools_processadas.append(p_item)

pnl_global = total_valor_atual - total_investido
roi_global = (pnl_global / total_investido * 100) if total_investido > 0 else 0.0

# -----------------------------------------------------------------------------
# 6. PAINEL DE MÉTRICAS PRINCIPAIS (KPIs)
# -----------------------------------------------------------------------------
st.title("⚡ Painel de Desempenho de Liquidez")

c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)

c_kpi1.metric("Investimento Total", f"${total_investido:,.2f}")
c_kpi2.metric("Valor em Carteira", f"${total_valor_atual:,.2f}", delta=f"${pnl_global:,.2f}")
c_kpi3.metric("ROI Acumulado", f"{roi_global:.2f}%", delta=f"{roi_global:.2f}%")
c_kpi4.metric("Estado das Pools", f"🟢 {total_ativas} | 🔴 {total_inativas}")

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7. POSIÇÕES ATIVAS & CARDS DETALHADOS
# -----------------------------------------------------------------------------
st.subheader("📋 Posições em Monitorização")

# Aplicar filtro
pools_filtradas = pools_processadas
if filtro_estado == "Ativas 🟢":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Ativa"]
elif filtro_estado == "Fora de Range 🔴":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") != "Ativa"]

if not pools_filtradas:
    st.info("Nenhuma piscina encontrada com o filtro selecionado.")
else:
    for p in pools_filtradas:
        par = p.get("par", "Par Não Identificado")
        estado = p.get("estado", "Ativa")
        p_nat = to_float(p.get("preco_nativo"))
        r_min = to_float(p.get("range_min"))
        r_max = to_float(p.get("range_max"))
        v_inv = to_float(p.get("valor_investido"))
        v_atual = p["v_atual"]
        pnl_pool = p["pnl_pool"]
        roi_pool = p["roi_pool"]
        addr = p.get("wallet_address", "")

        is_active = (estado == "Ativa")
        badge_html = '<span class="badge-active">🟢 EM RANGE</span>' if is_active else '<span class="badge-inactive">🔴 FORA DE RANGE</span>'
        card_class = "pool-card pool-card-active" if is_active else "pool-card pool-card-inactive"

        with st.container():
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin:0; font-size: 1.3rem;">{par}</h3>
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            col_a, col_b, col_c, col_d, col_e = st.columns(5)
            col_a.metric("Preço Nativo", f"{p_nat:.6f}")
            col_b.metric("Range Definição", f"{r_min:.6f} - {r_max:.6f}")
            col_c.metric("Valor Investido", f"${v_inv:,.2f}")
            col_d.metric("Valor Atual", f"${v_atual:,.2f}")
            col_e.metric("PnL ($ / %)", f"${pnl_pool:,.2f}", delta=f"{roi_pool:.2f}%")

            if addr:
                st.markdown(f"[🔍 Abrir no DexScreener](https://dexscreener.com/search?q={addr})")
            st.markdown("---")

# -----------------------------------------------------------------------------
# 8. ANÁLISE GRÁFICA & ALOCAÇÃO
# -----------------------------------------------------------------------------
st.subheader("📊 Análise e Alocação do Portfólio")

col_g1, col_g2 = st.columns(2)

with col_g1:
    # Gráfico de Torta (Alocação de Ativos)
    if pools_processadas:
        df_pie = pd.DataFrame(pools_processadas)
        fig_pie = px.pie(
            df_pie, 
            names="par", 
            values="v_atual", 
            title="Distribuição do Capital por Pool",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
        st.plotly_chart(fig_pie, use_container_width=True)

with col_g2:
    # Evolução Histórica (Area Chart)
    hist_data = get_historico_pnl()
    if hist_data:
        df_hist = pd.DataFrame(hist_data)
        fig_hist = px.area(
            df_hist, 
            x="data", 
            y="valor_total_usd", 
            title="Evolução do Valor Total ($ USD)",
            markers=True
        )
        fig_hist.update_traces(line_color="#10b981", fillcolor="rgba(16, 185, 129, 0.1)")
        fig_hist.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("Gráfico histórico a aguardar primeiras execuções do GitHub Action.")

# -----------------------------------------------------------------------------
# 9. GESTÃO DE POOLS & TABELA DADOS
# -----------------------------------------------------------------------------
with st.expander("⚙️ Gestão de Pools (Adicionar Nova / Tabela Completa)"):
    tab_add, tab_table = st.tabs(["➕ Adicionar Pool", "📄 Ver Tabela Resumo"])

    with tab_add:
        with st.form("form_add_pool"):
            c1, c2, c3 = st.columns(3)
            par_in = c1.text_input("Nome do Par (ex: PUMP/SOL)", "")
            addr_in = c2.text_input("Pair Address (DexScreener)", "")
            invest_in = c3.number_input("Valor Investido ($ USD)", min_value=0.0, step=10.0)

            c4, c5, c6 = st.columns(3)
            rmin_in = c4.number_input("Range Mínimo", min_value=0.0, format="%.8f")
            rmax_in = c5.number_input("Range Máximo", min_value=0.0, format="%.8f")
            qtd_in = c6.number_input("Quantidade de Tokens", min_value=0.0, step=0.1)

            btn_save = st.form_submit_button("Salvar Pool")

            if btn_save:
                if not par_in or not addr_in:
                    st.warning("Preencha o nome do par e a morada (Pair Address).")
                else:
                    p_usd, p_nat = fetch_dexscreener_data(addr_in)
                    payload = {
                        "par": par_in,
                        "wallet_address": addr_in,
                        "valor_investido": invest_in,
                        "range_min": rmin_in,
                        "range_max": rmax_in,
                        "quantidade": qtd_in,
                        "preco_atual": p_usd or 0,
                        "preco_nativo": p_nat or 0,
                        "estado": "Ativa"
                    }
                    res = requests.post(f"{SUPABASE_URL}/rest/v1/pools", headers=headers, json=payload)
                    if res.status_code in [200, 201]:
                        st.success("Pool adicionada com sucesso!")
                        st.rerun()
                    else:
                        st.error(f"Erro ao guardar: {res.text}")

    with tab_table:
        if pools:
            df_display = pd.DataFrame(pools)
            cols = ["id", "par", "estado", "preco_nativo", "range_min", "range_max", "valor_investido", "quantidade", "wallet_address"]
            cols_exist = [c for c in cols if c in df_display.columns]
            st.dataframe(df_display[cols_exist], use_container_width=True, hide_index=True)
