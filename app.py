import os
import time
import math
import random
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
    apr_ativo = ((v_fees / v_inv) / dias_ativos * 365 * 100) if v_inv > 0 else 0.0

    if estado != "Fechada":
        total_investido += v_inv
        total_valor_atual += v_atual_final
        total_fees += v_fees
        total_fees_diarias_corridas += fees_dia_corrido
        total_fees_diarias_ativas += fees_dia_ativo

    if estado == "Ativa":
        total_ativas += 1
    elif estado == "Inativa":
        total_inativas += 1
    elif estado == "Fechada":
        total_fechadas += 1

    p_item = p.copy()
    p_item["v_inicial_calc"] = v_inv
    p_item["v_atual_calc"] = v_atual_final
    p_item["fees_calc"] = v_fees
    p_item["pnl_pool"] = pnl_pool
    p_item["roi_pool"] = roi_pool
    p_item["dias_corridos"] = dias_corridos
    p_item["dias_ativos"] = dias_ativos
    p_item["fees_dia_corrido"] = fees_dia_corrido
    p_item["apr_corrido"] = apr_corrido
    p_item["fees_dia_ativo"] = fees_dia_ativo
    p_item["apr_ativo"] = apr_ativo
    pools_processadas.append(p_item)

valor_total_com_fees = total_valor_atual + total_fees
pnl_global = valor_total_com_fees - total_investido
roi_global = (pnl_global / total_investido * 100) if total_investido > 0 else 0.0

if st.sidebar.button("📲 Resumo no Telegram", use_container_width=True):
    msg_resumo = (
        f"📊 <b>PORTFÓLIO DEFI</b>\n\n"
        f"💰 <b>Investido:</b> ${total_investido:,.2f}\n"
        f"💵 <b>Atual:</b> ${total_valor_atual:,.2f}\n"
        f"💸 <b>Fees:</b> ${total_fees:,.2f}\n"
        f"📈 <b>PnL:</b> ${pnl_global:,.2f} ({roi_global:.2f}%)\n"
        f"📌 <b>Ativas:</b> 🟢 {total_ativas} | 🔴 {total_inativas} | 📁 {total_fechadas}"
    )
    if send_telegram(msg_resumo):
        st.sidebar.success("Enviado!")

# -----------------------------------------------------------------------------
# 6. EXIBIÇÃO DE KPIS
# -----------------------------------------------------------------------------
st.title("⚡ Liquidity Hub Pro")

k1, k2, k3 = st.columns(3)
k1.metric("Investimento Ativo", f"${total_investido:,.2f}")
k2.metric("Valor em Pools", f"${total_valor_atual:,.2f}")
k3.metric("Fees Totais 💸", f"${total_fees:,.2f}")

k4, k5, k6 = st.columns(3)
k4.metric("Fees / Dia (Corrido)", f"${total_fees_diarias_corridas:,.2f}/d")
k5.metric("PnL Total (+Fees)", f"${pnl_global:,.2f}", delta=f"{roi_global:.2f}%")
k6.metric("Estado das Pools", f"🟢 {total_ativas} | 🔴 {total_inativas} | 📁 {total_fechadas}")

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7. POSIÇÕES EM MONITORIZAÇÃO
# -----------------------------------------------------------------------------
st.subheader("📋 Posições em Monitorização")

pools_filtradas = pools_processadas
if filtro_estado == "Apenas Abertas (Ativas/Fora)":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") != "Fechada"]
elif filtro_estado == "Ativas 🟢":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Ativa"]
elif filtro_estado == "Fora de Range 🔴":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Inativa"]
elif filtro_estado == "Fechadas 📁":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Fechada"]

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
        
        dias_corridos = p["dias_corridos"]
        dias_ativos = p["dias_ativos"]
        fees_dia_corrido = p["fees_dia_corrido"]
        apr_corrido = p["apr_corrido"]
        fees_dia_ativo = p["fees_dia_ativo"]
        apr_ativo = p["apr_ativo"]
        
        hrs_inativa = to_float(p.get("horas_inativa"))
        addr = p.get("wallet_address", "")

        tipo_desvio = "EM RANGE"
        if r_max > 0 and p_nat > r_max:
            pct = ((p_nat - r_max) / r_max) * 100
            tipo_desvio = f"+{pct:.2f}% máx"
        elif r_min > 0 and p_nat < r_min:
            pct = ((r_min - p_nat) / r_min) * 100
            tipo_desvio = f"-{pct:.2f}% mín"

        if estado == "Ativa":
            badge_html = '<span class="badge-active">🟢 EM RANGE</span>'
            card_class = "pool-card pool-card-active"
        elif estado == "Inativa":
            badge_html = f'<span class="badge-inactive">🔴 FORA ({tipo_desvio} | {hrs_inativa:.1f}h)</span>'
            card_class = "pool-card pool-card-inactive"
        else:
            badge_html = '<span class="badge-closed">📁 FECHADA</span>'
            card_class = "pool-card pool-card-closed"

        with st.container():
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <h3 style="margin:0;">{par} <span style="font-size: 0.8rem; color: #a0aec0;">({dias_corridos:.0f}d corridos / {dias_ativos:.1f}d ativos)</span></h3>
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            c_p1, c_p2, c_p3, c_p4 = st.columns(4)
            c_p1.metric("Preço Nativo", format_crypto_price(p_nat), delta=f"${p_usd:.4f}" if p_usd > 0 else None)
            c_p2.metric("Range Definição", f"{format_crypto_price(r_min)} - {format_crypto_price(r_max)}")
            c_p3.metric("Investido / Atual", f"${v_inv:,.0f} /${v_at:,.0f}")
            c_p4.metric("Fees Totais", f"${v_fees:,.2f}")

            if estado != "Fechada":
                render_sparkline_chart(p_nat, r_min, r_max)

            c_p5, c_p6, c_p7, c_p8 = st.columns(4)
            c_p5.metric("Dia Corrido", f"${fees_dia_corrido:,.2f}/d", delta=f"{apr_corrido:.1f}% APR")
            c_p6.metric("Dia Efetivo", f"${fees_dia_ativo:,.2f}/d", delta=f"{apr_ativo:.1f}% APR")
            c_p7.metric("PnL Total (+Fees)", f"${pnl_pool:,.2f}", delta=f"{roi_pool:.2f}%")
            if addr:
                c_p8.markdown(f"<br>[🔍 DexScreener](https://dexscreener.com/search?q={addr})", unsafe_allow_html=True)

            st.markdown("---")

# -----------------------------------------------------------------------------
# 8. GRÁFICOS
# -----------------------------------------------------------------------------
st.subheader("📊 Análise do Portfólio")
col_g1, col_g2 = st.columns(2)

with col_g1:
    pools_abertas = [p for p in pools_processadas if p.get("estado") != "Fechada"]
    if pools_abertas:
        df_pie = pd.DataFrame(pools_abertas)
        fig_pie = px.pie(
            df_pie, 
            names="par", 
            values="v_atual_calc", 
            title="Distribuição do Capital Ativo por Pool",
            hole=0.4
        )
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", margin=dict(l=10, r=10, t=40, b=10))
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
        fig_hist.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("A aguardar histórico de PnL...")

# -----------------------------------------------------------------------------
# 9. FERRAMENTAS & GESTÃO
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🛠️ Ferramentas & Gestão")

tab_add, tab_edit, tab_calc, tab_table = st.tabs([
    "➕ Adicionar", 
    "✏ Editar / Fechar", 
    "🧮 Calculadora & IL", 
    "📄 Tabela Geral"
])

with tab_add:
    with st.form("form_add_pool"):
        c1, c2, c3 = st.columns(3)
        par_in = c1.text_input("Par (ex: PUMP/SOL)", "")
        addr_in = c2.text_input("Pair Address", "")
        invest_in = c3.number_input("Valor Inicial ($ USD)", min_value=0.0, step=10.0)

        c4, c5, c6 = st.columns(3)
        rmin_in = c4.number_input("Range Mínimo", min_value=0.0, format="%.8f")
        rmax_in = c5.number_input("Range Máximo", min_value=0.0, format="%.8f")
        v_atual_in = c6.number_input("Valor Atual ($ USD)", min_value=0.0, step=10.0)
        
        c7, c8 = st.columns(2)
        fees_in = c7.number_input("Fees Geradas ($ USD)", min_value=0.0, step=1.0)
        data_ent_in = c8.text_input("Data Entrada (YYYY-MM-DD)", value=datetime.now().strftime('%Y-%m-%d'))

        btn_save = st.form_submit_button("Salvar Nova Pool")

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
                    st.success("Pool adicionada!")
                    st.rerun()

with tab_edit:
    if not pools:
        st.info("Não existem pools para editar.")
    else:
        lista_opcoes = {f"ID {p['id']} - {p.get('par', 'N/A')} [{p.get('estado', 'Ativa')}]": p for p in pools}
        escolha = st.selectbox("Selecione a Pool:", list(lista_opcoes.keys()))
        pool_sel = lista_opcoes[escolha]
        
        with st.form("form_edit_pool"):
            st.markdown(f"**Editar Posição ID {pool_sel['id']} ({pool_sel.get('par')})**")
            
            estado_opcoes = ["Ativa", "Inativa", "Fechada"]
            estado_atual_idx = estado_opcoes.index(pool_sel.get("estado", "Ativa")) if pool_sel.get("estado") in estado_opcoes else 0
            e_estado = st.selectbox("Estado da Pool:", estado_opcoes, index=estado_atual_idx)

            e1, e2, e3 = st.columns(3)
            e_val_atual = e1.number_input("Valor Atual ($)", value=to_float(pool_sel.get("valor_atual")), step=10.0)
            e_fees = e2.number_input("Fees Acumuladas ($)", value=to_float(pool_sel.get("fees")), step=1.0)
            e_data_ent = e3.text_input("Data Entrada", value=str(pool_sel.get("data_entrada", "")))

            e4, e5, e6 = st.columns(3)
            e_rmin = e4.number_input("Range Mínimo", value=to_float(pool_sel.get("range_min")), format="%.8f")
            e_rmax = e5.number_input("Range Máximo", value=to_float(pool_sel.get("range_max")), format="%.8f")
            e_hrs_inativa = e6.number_input("Horas Inativa", value=to_float(pool_sel.get("horas_inativa")), step=1.0)

            btn_update = st.form_submit_button("💾 Guardar Alterações")

            if btn_update:
                patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_sel['id']}"
                update_payload = {
                    "estado": e_estado,
                    "valor_atual": e_val_atual,
                    "fees": e_fees,
                    "data_entrada": e_data_ent,
                    "range_min": e_rmin,
                    "range_max": e_rmax,
                    "horas_inativa": e_hrs_inativa
                }
                res = requests.patch(patch_url, headers=headers, json=update_payload)
                if res.status_code in [200, 204]:
                    st.success("Atualizado com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao guardar: {res.text}")

        st.markdown("---")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.markdown("#### 🔒 Encerrar Rápido (Marcar Fechada)")
            st.caption("Muda o estado diretamente para 'Fechada' no Supabase.")
            if st.button(f"🔒 Marcar {pool_sel.get('par')} como Fechada", use_container_width=True):
                patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_sel['id']}"
                res = requests.patch(patch_url, headers=headers, json={"estado": "Fechada"})
                if res.status_code in [200, 204]:
                    st.success(f"Pool {pool_sel.get('par')} marcada como Fechada!")
                    st.rerun()
                else:
                    st.error(f"Erro Supabase ({res.status_code}): {res.text}")

        with col_f2:
            st.markdown("#### 🚨 Eliminar Definitivamente")
            st.caption("Remove permanentemente esta posição da base de dados Supabase.")
            if st.button(f"🗑️ Eliminar Permanente ID {pool_sel['id']}", type="primary", use_container_width=True):
                del_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_sel['id']}"
                del_res = requests.delete(del_url, headers=headers)
                if del_res.status_code in [200, 204]:
                    st.success("Pool eliminada!")
                    st.rerun()

# TAB 3: Calculadora de Rebalanceamento & IL (CORRIGIDA)
with tab_calc:
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("#### 🎯 Calculadora de Novos Ranges")
        p_ref = st.number_input("Preço Nativo Atual", min_value=0.0, value=0.000053, format="%.8f", key="calc_p_ref")
        var_pct = st.slider("Amplitude (± %)", min_value=1.0, max_value=50.0, value=15.0, step=0.5, key="calc_var_pct")

        if p_ref > 0:
            novo_min = p_ref * (1 - (var_pct / 100))
            novo_max = p_ref * (1 + (var_pct / 100))
            st.write(f"**Novo Range Mínimo (-{var_pct}%):** `{format_crypto_price(novo_min)}`")
            st.write(f"**Novo Range Máximo (+{var_pct}%):** `{format_crypto_price(novo_max)}`")

    with col_c2:
        st.markdown("#### 📉 Simulador de IL")
        var_preco_simulada = st.slider("Variação de Preço (%)", min_value=-80.0, max_value=300.0, value=20.0, step=5.0, key="calc_il_slider")
        razao = 1.0 + (var_preco_simulada / 100.0)
        il_resultado = calcular_il(razao)
        st.metric("IL Estimada", f"{il_resultado:.2f}%", delta=f"{il_resultado:.2f}%", delta_color="inverse")

# TAB 4: Tabela Resumo (CORRIGIDA COM HIGIENIZAÇÃO DE DADOS)
with tab_table:
    if pools:
        df_table = pd.DataFrame(pools)
        # Preencher valores nulos para evitar falhas de visualização no Pandas/Streamlit
        df_table = df_table.fillna("")
        st.dataframe(df_table, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma posição registada na base de dados.")
