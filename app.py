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
# 3. FUNÇÕES AUXILIARES & APIS PÚBLICAS
# -----------------------------------------------------------------------------
def normalizar_estado(estado_raw):
    e = str(estado_raw or "").strip().lower()
    if "fechad" in e or "closed" in e or "fechada" in e:
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

# -----------------------------------------------------------------------------
# CÁLCULO DE IL PONDERADO PARA POOLS SIMÉTRICAS OU ASSIMÉTRICAS
# -----------------------------------------------------------------------------
def calcular_il_ponderado(preco_nativo_inicial, preco_nativo_atual, peso_a=0.5):
    p_ini = to_float(preco_nativo_inicial)
    p_at = to_float(preco_nativo_atual)
    wa = to_float(peso_a, 0.5)

    if p_ini <= 0 or p_at <= 0:
        return 0.0

    wb = 1.0 - wa
    ratio = p_at / p_ini

    val_hodl = (wa * ratio) + wb
    val_lp = ratio ** wa

    if val_hodl <= 0:
        return 0.0

    il_pct = ((val_lp / val_hodl) - 1) * 100
    return il_pct

def calcular_dias_para_anular_il(il_usd, fees_dia_media):
    if fees_dia_media <= 0 or il_usd <= 0:
        return 0.0
    return il_usd / fees_dia_media

# -----------------------------------------------------------------------------
# 4. BARRA LATERAL & OPÇÕES
# -----------------------------------------------------------------------------
pools = get_pools()

st.sidebar.title("⚡ DeFi Hub Pro")
filtro_estado = st.sidebar.selectbox("Filtrar Posições:", ["Apenas Abertas (Ativas/Fora)", "Ativas 🟢", "Fora de Range 🔴", "Todas"])

esconder_detalhes = st.sidebar.checkbox("👁️ Ocultar Detalhes das Pools", value=False)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Sincronizar Tudo", use_container_width=True):
    with st.spinner("A atualizar posições abertas..."):
        agora = time.time()
        for p in pools:
            estado_anterior = normalizar_estado(p.get("estado"))
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
                        desvio_txt = f"+{pct:.2f}% (Acima do Máximo)"
                    elif r_min > 0 and p_nat < r_min:
                        in_range = False
                        pct = ((r_min - p_nat) / r_min) * 100
                        desvio_txt = f"-{pct:.2f}% (Abaixo do Mínimo)"
                    
                    novo_estado = "Ativa" if in_range else "Inativa"
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
total_fees_sacadas = 0.0
total_fees_por_recolher = 0.0
total_fees = 0.0
total_fees_diarias_corridas = 0.0
total_fees_diarias_ativas = 0.0
total_ativas = 0
total_inativas = 0

pools_processadas = []

for p in pools:
    v_inv = to_float(p.get("valor_inicial"))
    v_at = to_float(p.get("valor_atual"))
    v_fees_sacadas = to_float(p.get("fees"))
    v_fees_por_recolher = to_float(p.get("position_pubkey"))
    data_ent = p.get("data_entrada", "")
    hrs_inativa = to_float(p.get("horas_inativa"))
    estado = normalizar_estado(p.get("estado"))

    p_nat_atual = to_float(p.get("preco_nativo"))
    p_nat_inicial = to_float(p.get("preco_inicial"))
    
    # Peso do Token A (se não definido na BD, assume 0.5 padrão)
    peso_a = to_float(p.get("peso_a"), 0.5)
    if peso_a <= 0:
        peso_a = 0.5

    il_pct = calcular_il_ponderado(p_nat_inicial, p_nat_atual, peso_a)
    il_usd = abs(il_pct / 100.0) * v_inv

    v_fees_totais_pool = v_fees_sacadas + v_fees_por_recolher
    v_atual_final = v_at if v_at > 0 else v_inv

    pnl_pool = (v_atual_final + v_fees_totais_pool) - v_inv
    roi_pool = (pnl_pool / v_inv * 100) if v_inv > 0 else 0.0

    dias_corridos, dias_ativos = calcular_dias_metricas(data_ent, hrs_inativa)
    
    fees_dia_corrido = v_fees_totais_pool / dias_corridos
    apr_corrido = ((v_fees_totais_pool / v_inv) / dias_corridos * 365 * 100) if v_inv > 0 else 0.0

    fees_dia_ativo = v_fees_totais_pool / dias_ativos
    apr_ativo = ((v_fees_totais_pool / v_inv) / dias_ativos * 365 * 100) if v_inv > 0 else 0.0

    dias_cobertura = calcular_dias_para_anular_il(il_usd, fees_dia_corrido)

    total_investido += v_inv
    total_valor_atual += v_atual_final
    total_fees_sacadas += v_fees_sacadas
    total_fees_por_recolher += v_fees_por_recolher
    total_fees += v_fees_totais_pool
    total_fees_diarias_corridas += fees_dia_corrido
    total_fees_diarias_ativas += fees_dia_ativo

    if estado == "Ativa":
        total_ativas += 1
    else:
        total_inativas += 1

    p_item = p.copy()
    p_item["estado"] = estado
    p_item["v_inicial_calc"] = v_inv
    p_item["v_atual_calc"] = v_atual_final
    p_item["fees_sacadas_calc"] = v_fees_sacadas
    p_item["fees_por_recolher_calc"] = v_fees_por_recolher
    p_item["fees_calc"] = v_fees_totais_pool
    p_item["il_pct_calc"] = il_pct
    p_item["il_usd_calc"] = il_usd
    p_item["dias_cobertura_calc"] = dias_cobertura
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

if st.sidebar.button("📸 Guardar Snapshot Diário", use_container_width=True):
    hoje = datetime.now().strftime('%Y-%m-%d')
    payload_pnl = {
        "data": hoje,
        "valor_total_usd": round(valor_total_com_fees, 2)
    }
    res = requests.post(f"{SUPABASE_URL}/rest/v1/historico_pnl", headers=headers, json=payload_pnl)
    if res.status_code in [200, 201]:
        st.sidebar.success(f"Snapshot de {hoje} (${valor_total_com_fees:,.2f}) guardado!")
        time.sleep(1)
        st.rerun()
    else:
        st.sidebar.error("Erro ao guardar snapshot no Supabase.")

if st.sidebar.button("📲 Resumo no Telegram", use_container_width=True):
    msg_resumo = (
        f"📊 <b>PORTFÓLIO DEFI</b>\n\n"
        f"💰 <b>Investido:</b> ${total_investido:,.2f}\n"
        f"💵 <b>Atual:</b> ${total_valor_atual:,.2f}\n"
        f"💸 <b>Fees Totais:</b> ${total_fees:,.2f} (${total_fees_sacadas:,.2f} sacadas)\n"
        f"📈 <b>PnL:</b> ${pnl_global:,.2f} ({roi_global:.2f}%)\n"
        f"📌 <b>Ativas:</b> 🟢 {total_ativas} | 🔴 {total_inativas}"
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
k3.metric("Fees Totais 💸", f"${total_fees:,.2f}", delta=f"${total_fees_sacadas:,.2f} sacadas")

k4, k5, k6 = st.columns(3)
k4.metric("Fees / Dia (Corrido)", f"${total_fees_diarias_corridas:,.2f}/d")
k5.metric("PnL Total (+Fees)", f"${pnl_global:,.2f}", delta=f"{roi_global:.2f}%")
k6.metric("Estado das Pools", f"🟢 {total_ativas} | 🔴 {total_inativas}")

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7. POSIÇÕES EM MONITORIZAÇÃO
# -----------------------------------------------------------------------------
st.subheader("📋 Posições em Monitorização")

pools_filtradas = pools_processadas
if filtro_estado == "Ativas 🟢":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Ativa"]
elif filtro_estado == "Fora de Range 🔴":
    pools_filtradas = [p for p in pools_processadas if p.get("estado") == "Inativa"]

if not pools_filtradas:
    st.info("Nenhuma piscina encontrada com o filtro selecionado.")
else:
    for p in pools_filtradas:
        pool_id = p["id"]
        par = p.get("par", "Par N/A")
        estado = p.get("estado", "Ativa")
        p_nat = to_float(p.get("preco_nativo"))
        p_usd = to_float(p.get("preco_atual"))
        r_min = to_float(p.get("range_min"))
        r_max = to_float(p.get("range_max"))
        v_inv = p["v_inicial_calc"]
        v_at = p["v_atual_calc"]
        v_fees_sacadas = p["fees_sacadas_calc"]
        v_fees_por_recolher = p["fees_por_recolher_calc"]
        v_fees_totais = p["fees_calc"]
        
        il_pct = p["il_pct_calc"]
        il_usd = p["il_usd_calc"]
        dias_cobertura = p["dias_cobertura_calc"]

        pnl_pool = p["pnl_pool"]
        roi_pool = p["roi_pool"]
        
        dias_corridos = p["dias_corridos"]
        dias_ativos = p["dias_ativos"]
        fees_dia_corrido = p["fees_dia_corrido"]
        apr_corrido = p["apr_corrido"]
        
        hrs_inativa = to_float(p.get("horas_inativa"))

        tipo_desvio = "EM RANGE"
        motivo_saida = ""
        if r_max > 0 and p_nat > r_max:
            pct = ((p_nat - r_max) / r_max) * 100
            tipo_desvio = f"+{pct:.2f}% (Acima)"
            motivo_saida = "⚠️ Saída pelo limite SUPERIOR."
        elif r_min > 0 and p_nat < r_min:
            pct = ((r_min - p_nat) / r_min) * 100
            tipo_desvio = f"-{pct:.2f}% (Abaixo)"
            motivo_saida = "⚠️ Saída pelo limite INFERIOR."

        if estado == "Ativa":
            badge_html = '<span class="badge-active">🟢 EM RANGE</span>'
            card_class = "pool-card pool-card-active"
        else:
            badge_html = f'<span class="badge-inactive">🔴 FORA ({tipo_desvio} | {hrs_inativa:.1f}h)</span>'
            card_class = "pool-card pool-card-inactive"

        with st.container():
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin:0;">{par} <span style="font-size: 0.8rem; color: #a0aec0;">({dias_corridos:.0f}d corridos / {dias_ativos:.1f}d ativos)</span></h3>
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if not esconder_detalhes:
                c_p1, c_p2, c_p3, c_p4 = st.columns(4)
                c_p1.metric("Preço Nativo", format_crypto_price(p_nat), delta=f"${p_usd:.4f}" if p_usd > 0 else None)
                c_p2.metric("Range Definição", f"{format_crypto_price(r_min)} - {format_crypto_price(r_max)}")
                c_p3.metric("Investido / Atual", f"${v_inv:,.0f} /${v_at:,.0f}")
                
                c_p4.metric(
                    "Perda Impermanente (IL)", 
                    f"{il_pct:.2f}% (${il_usd:,.2f})", 
                    delta=f"{dias_cobertura:.1f} dias p/ anular" if il_usd > 0 else "0 dias", 
                    delta_color="inverse"
                )

                if motivo_saida and estado != "Ativa":
                    st.caption(motivo_saida)

                render_sparkline_chart(p_nat, r_min, r_max)

                c_p5, c_p6, c_p7, c_p8 = st.columns(4)
                c_p5.metric("Fees Sacadas", f"${v_fees_sacadas:,.2f}")
                c_p6.metric("Fees Por Recolher", f"${v_fees_por_recolher:,.2f}")
                c_p7.metric("Rendimento Diário", f"${fees_dia_corrido:,.2f}/d", delta=f"{apr_corrido:.1f}% APR")
                c_p8.metric("PnL Total (+Fees)", f"${pnl_pool:,.2f}", delta=f"{roi_pool:.2f}%")

                with st.expander(f"💸 Registo Rápido de Saque — {par}"):
                    key_input = f"input_saque_{pool_id}"
                    if key_input not in st.session_state:
                        st.session_state[key_input] = 0.0

                    col_saque_val, col_saque_btn = st.columns([3, 1])
                    val_saque_hoje = col_saque_val.number_input(
                        "Valor das fees sacadas hoje ($ USD):", 
                        min_value=0.0, 
                        step=1.0, 
                        key=key_input
                    )
                    
                    if col_saque_btn.button("⚡ Registar Saque", key=f"btn_saque_{pool_id}", use_container_width=True):
                        if val_saque_hoje > 0:
                            novas_fees_sacadas = v_fees_sacadas + val_saque_hoje
                            patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
                            res = requests.patch(patch_url, headers=headers, json={"fees": novas_fees_sacadas})
                            if res.status_code in [200, 204]:
                                st.session_state[key_input] = 0.0
                                st.success(f"Adicionados +${val_saque_hoje:,.2f} em fees sacadas de {par}!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar o Supabase.")

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
            title="Distribuição do Capital Ativo por Pool",
            hole=0.4
        )
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0
