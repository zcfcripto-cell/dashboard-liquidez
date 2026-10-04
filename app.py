import os
import time
from datetime import datetime
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA & ESTILOS CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="DeFi Liquidity Hub Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700 !important; }
    .pool-card {
        background-color: #1a1f2c;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #2d3748;
        margin-bottom: 16px;
    }
    .pool-card-active { border-left: 5px solid #10b981; }
    .pool-card-inactive { border-left: 5px solid #ef4444; }
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
# 2. LIGAÇÃO AO SUPABASE & CREDENCIAIS
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
# 3. FUNÇÕES AUXILIARES
# -----------------------------------------------------------------------------
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
    except Exception as e:
        st.error(f"Erro no DexScreener: {e}")
    return None, None

def get_pools():
    url = f"{SUPABASE_URL}/rest/v1/pools?select=*&order=id.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Erro ao carregar pools: {e}")
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

# -----------------------------------------------------------------------------
# 4. BARRA LATERAL & FILTROS
# -----------------------------------------------------------------------------
pools = get_pools()

st.sidebar.title("⚡ DeFi Hub Pro")
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
                        "preco_nativo": p_nat,
                        "estado": novo_estado,
                        "last_price_update": time.time()
                    }
                    if p_usd:
                        patch_data["preco_atual"] = p_usd
                        
                    requests.patch(patch_url, headers=headers, json=patch_data)
    st.sidebar.success("Atualizado com sucesso!")
    st.rerun()

# -----------------------------------------------------------------------------
# 5. CÁLCULO DE MÉTRICAS COMPLETO
# -----------------------------------------------------------------------------
total_investido = 0.0
total_valor_atual = 0.0
total_fees = 0.0
total_ativas = 0
total_inativas = 0

pools_processadas = []

for p in pools:
    v_inv = to_float(p.get("valor_inicial"))
    v_at = to_float(p.get("valor_atual"))
    v_fees = to_float(p.get("fees"))
    
    v_atual_final = v_at if v_at > 0 else v_inv
    
    pnl_pool = (v_atual_final + v_fees) - v_inv
    roi_pool = (pnl_pool / v_inv * 100) if v_inv > 0 else 0.0

    total_investido += v_inv
    total_valor_atual += v_atual_final
    total_fees += v_fees

    estado = p.get("estado", "Ativa")
    if estado == "Ativa":
        total_ativas += 1
    else:
        total_inativas += 1

    p_item = p.copy()
    p_item["v_inicial_calc"] = v_inv
    p_item["v_atual_calc"] = v_atual_final
    p_item["fees_calc"] = v_fees
    p_item["pnl_pool"] = pnl_pool
    p_item["roi_pool"] = roi_pool
    pools_processadas.append(p_item)

valor_total_com_fees = total_valor_atual + total_fees
pnl_global = valor_total_com_fees - total_investido
roi_global = (pnl_global / total_investido * 100) if total_investido > 0 else 0.0

# -----------------------------------------------------------------------------
# 6. EXIBIÇÃO DE KPIS
# -----------------------------------------------------------------------------
st.title("⚡ Painel de Desempenho de Liquidez")

c_kpi1, c_kpi2, c_kpi3, c_kpi4, c_kpi5 = st.columns(5)
c_kpi1.metric("Investimento Total", f"${total_investido:,.2f}")
c_kpi2.metric("Valor em Pools", f"${total_valor_atual:,.2f}")
c_kpi3.metric("Fees Geradas 💸", f"${total_fees:,.2f}")
c_kpi4.metric("PnL Total (+Fees)", f"${pnl_global:,.2f}", delta=f"{roi_global:.2f}%")
c_kpi5.metric("Estado das Pools", f"🟢 {total_ativas} | 🔴 {total_inativas}")

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7. POSIÇÕES EM MONITORIZAÇÃO (Com Horas Inativa & Last Update)
# -----------------------------------------------------------------------------
st.subheader("📋 Posições em Monitorização")

pools_filtradas = pools_processadas
if filtro_estado == "Ativas 🟢":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Ativa"]
elif filtro_estado == "Fora de Range 🔴":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") != "Ativa"]

if not pools_filtradas:
    st.info("Nenhuma piscina encontrada com o filtro selecionado.")
else:
    for p in pools_filtradas:
        par = p.get("par", "Par N/A")
        estado = p.get("estado", "Ativa")
        p_nat = to_float(p.get("preco_nativo"))
        p_usd = to_float(p.get("preco_atual"))
        r_min = to_float(p.get("range_min"))
        r_max = to_float(p.get("range_max"))
        v_inv = p["v_inicial_calc"]
        v_at = p["v_atual_calc"]
        v_fees = p["fees_calc"]
        pnl_pool = p["pnl_pool"]
        roi_pool = p["roi_pool"]
        data_ent = p.get("data_entrada", "N/A")
        hrs_inativa = to_float(p.get("horas_inativa"))
        last_upd = p.get("last_price_update")
        addr = p.get("wallet_address", "")

        # Formatação de data da última atualização
        last_upd_str = "N/A"
        if last_upd and to_float(last_upd) > 0:
            try:
                last_upd_str = datetime.fromtimestamp(to_float(last_upd)).strftime('%Y-%m-%d %H:%M')
            except Exception:
                last_upd_str = str(last_upd)

        is_active = (estado == "Ativa")
        if is_active:
            badge_html = '<span class="badge-active">🟢 EM RANGE</span>'
        else:
            badge_html = f'<span class="badge-inactive">🔴 FORA DE RANGE ({hrs_inativa:.1f}h)</span>'
        
        card_class = "pool-card pool-card-active" if is_active else "pool-card pool-card-inactive"

        with st.container():
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin:0; font-size: 1.3rem;">{par} <span style="font-size: 0.85rem; color: #a0aec0; font-weight: normal;">(Entrada: {data_ent} | Atualizado: {last_upd_str})</span></h3>
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
            col_a.metric("Preço Nativo / USD", f"{p_nat:.6f}", delta=f"${p_usd:.4f}" if p_usd > 0 else None)
            col_b.metric("Range Definição", f"{r_min:.6f} - {r_max:.6f}")
            col_c.metric("Investido", f"${v_inv:,.2f}")
            col_d.metric("Valor Atual", f"${v_at:,.2f}")
            col_e.metric("Fees Geradas 💸", f"${v_fees:,.2f}")
            col_f.metric("PnL Total (+Fees)", f"${pnl_pool:,.2f}", delta=f"{roi_pool:.2f}%")

            if addr:
                st.markdown(f"[🔍 Abrir no DexScreener](https://dexscreener.com/search?q={addr})")
            st.markdown("---")

# -----------------------------------------------------------------------------
# 8. GRÁFICOS
# -----------------------------------------------------------------------------
st.subheader("📊 Análise do Portfólio")
col_g1, col_g2 = st.columns(2)

with col_g1:
    if pools_processadas:
        df_pie = pd.DataFrame(pools_processadas)
        fig_pie = px.pie(
            df_pie, 
            names="par", 
            values="v_atual_calc", 
            title="Distribuição do Capital por Pool",
            hole=0.4
        )
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
        st.plotly_chart(fig_pie, use_container_width=True)

with col_g2:
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
        st.info("A aguardar histórico de PnL...")

# -----------------------------------------------------------------------------
# 9. GESTÃO & TABELA COMPLETA
# -----------------------------------------------------------------------------
with st.expander("⚙️ Gestão de Pools (Adicionar Nova / Tabela Completa)"):
    tab_add, tab_table = st.tabs(["➕ Adicionar Pool", "📄 Ver Tabela Resumo"])

    with tab_add:
        with st.form("form_add_pool"):
            c1, c2, c3 = st.columns(3)
            par_in = c1.text_input("Nome do Par (ex: PUMP/SOL)", "")
            addr_in = c2.text_input("Pair Address (DexScreener)", "")
            invest_in = c3.number_input("Valor Inicial ($ USD)", min_value=0.0, step=10.0)

            c4, c5, c6 = st.columns(3)
            rmin_in = c4.number_input("Range Mínimo", min_value=0.0, format="%.8f")
            rmax_in = c5.number_input("Range Máximo", min_value=0.0, format="%.8f")
            v_atual_in = c6.number_input("Valor Atual ($ USD)", min_value=0.0, step=10.0)
            
            c7, c8 = st.columns(2)
            fees_in = c7.number_input("Fees Geradas ($ USD)", min_value=0.0, step=1.0)
            data_ent_in = c8.text_input("Data de Entrada (YYYY-MM-DD)", value="2026-10-05")

            btn_save = st.form_submit_button("Salvar Pool")

            if btn_save:
                if not par_in or not addr_in:
                    st.warning("Preencha o nome do par e a morada.")
                else:
                    p_usd, p_nat = fetch_dexscreener_data(addr_in)
                    payload = {
                        "par": par_in,
                        "wallet_address": addr_in,
                        "valor_inicial": invest_in,
                        "valor_atual": v_atual_in if v_atual_in > 0 else invest_in,
                        "fees": fees_in,
                        "data_entrada": data_ent_in,
                        "range_min": rmin_in,
                        "range_max": rmax_in,
                        "preco_nativo": p_nat or 0,
                        "preco_atual": p_usd or 0,
                        "estado": "Ativa",
                        "horas_inativa": 0.0
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
            st.dataframe(df_display, use_container_width=True, hide_index=True)
