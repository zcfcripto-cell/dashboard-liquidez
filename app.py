import os
import time
import math
import random
from datetime import datetime, date
from zoneinfo import ZoneInfo
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

# Âncora invisível exatamente no topo da página
st.markdown('<div id="topo-pagina"></div>', unsafe_allow_html=True)

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

    /* Botões Flutuantes (Topo e Fundo) */
    .scroll-btn-container {
        position: fixed;
        bottom: 25px;
        right: 25px;
        z-index: 999999;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    .scroll-btn {
        background-color: #1a1f2c;
        color: #38bdf8;
        border: 1px solid #2d3748;
        border-radius: 50%;
        width: 45px;
        height: 45px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        transition: all 0.2s ease-in-out;
        text-decoration: none;
    }
    .scroll-btn:hover {
        background-color: #38bdf8;
        color: #0e1117;
        transform: scale(1.08);
        border-color: #38bdf8;
    }

    @media (max-width: 768px) {
        div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
        div[data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
        .pool-card { padding: 10px; }
        h3 { font-size: 1.1rem !important; }
    }
</style>

<div class="scroll-btn-container">
    <a href="#topo-pagina" class="scroll-btn" title="Ir para o Topo">⬆️</a>
    <a href="#ferramentas-gestao" class="scroll-btn" title="Ir para o Fundo">⬇️</a>
</div>
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
def get_agora_pt():
    """Devolve a data e hora atual em Portugal Continental (Europe/Lisbon)."""
    return datetime.now(ZoneInfo("Europe/Lisbon"))

def normalizar_estado(estado_raw):
    e = str(estado_raw or "").strip().lower()
    if "fechad" in e or "closed" in e or "fechada" in e:
        return "Fechada"
    elif "inativ" in e or "fora" in e:
        return "Inativa"
    return "Ativa"

def identificar_tipo_protocolo(rede_str):
    r = str(rede_str or "").lower()
    if "meteora" in r or "dlmm" in r:
        return "DLMM (Meteora)"
    elif "uniswap" in r:
        return "CLMM (Uniswap v3)"
    else:
        return "CLMM (Raydium/Outros)"

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

def get_aportes():
    url = f"{SUPABASE_URL}/rest/v1/aportes?select=*&order=data_aporte.desc,id.desc"
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

def get_historico_fees():
    url = f"{SUPABASE_URL}/rest/v1/historico_fees?select=*&order=data.desc,id.desc"
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

def calcular_dias_metricas(data_str, horas_inativa, data_fecho_str=None):
    if not data_str:
        return 1.0, 1.0
    try:
        data_inicio = datetime.strptime(str(data_str).strip(), "%Y-%m-%d").date()
        if data_fecho_str:
            hoje_pt = datetime.strptime(str(data_fecho_str).strip(), "%Y-%m-%d").date()
        else:
            hoje_pt = get_agora_pt().date()
            
        dias_corridos = max((hoje_pt - data_inicio).days, 1)
        dias_inativos = to_float(horas_inativa) / 24.0
        dias_ativos = max(dias_corridos - dias_inativos, 0.1)
        return float(dias_corridos), float(dias_ativos)
    except Exception:
        return 1.0, 1.0

# -----------------------------------------------------------------------------
# CÁLCULO DE LIQUIDEZ CONCENTRADA (CLMM / DLMM) E CUSTO MÉDIO
# -----------------------------------------------------------------------------
def calcular_peso_clmm(p_atual, r_min, r_max):
    pa = to_float(p_atual)
    rmin = to_float(r_min)
    rmax = to_float(r_max)

    if rmin <= 0 or rmax <= 0 or rmin >= rmax:
        return 0.5

    if pa <= rmin:
        return 1.0
    if pa >= rmax:
        return 0.0

    try:
        sqrt_p = math.sqrt(pa)
        sqrt_min = math.sqrt(rmin)
        sqrt_max = math.sqrt(rmax)

        numerator = (sqrt_max - sqrt_p) / (sqrt_p * sqrt_max)
        denominator = (sqrt_max - sqrt_min) / (sqrt_min * sqrt_max)
        
        wa = numerator / denominator
        return max(0.0, min(1.0, wa))
    except Exception:
        return 0.5

def calcular_il_clmm(p_inicial, p_atual, r_min, r_max):
    p_ini = to_float(p_inicial)
    p_at = to_float(p_atual)

    if p_ini <= 0 or p_at <= 0:
        return 0.0

    wa = calcular_peso_clmm(p_at, r_min, r_max)
    wb = 1.0 - wa

    ratio = p_at / p_ini

    if wa == 1.0:
        return (p_at / p_ini - 1) * 100
    elif wa == 0.0:
        return 0.0

    val_hodl = (wa * ratio) + wb
    val_lp = ratio ** wa

    if val_hodl <= 0:
        return 0.0

    il_pct = ((val_lp / val_hodl) - 1) * 100
    return il_pct

def calcular_custo_medio_inferior_rigoroso(p_inicial, r_min, r_max):
    p_ini = to_float(p_inicial)
    rmin = to_float(r_min)
    rmax = to_float(r_max)
    
    if p_ini <= 0 or rmin <= 0 or rmax <= 0 or rmin >= rmax:
        return 0.0
    
    try:
        sqrt_p_ini = math.sqrt(p_ini)
        sqrt_rmin = math.sqrt(rmin)
        sqrt_rmax = math.sqrt(rmax)
        
        numerador = 2 * sqrt_p_ini - sqrt_rmin - (p_ini / sqrt_rmax)
        denominador = (1 / sqrt_rmin) - (1 / sqrt_rmax)
        
        if denominador == 0:
            return 0.0
            
        custo_medio = numerador / denominador
        return max(0.0, custo_medio)
    except Exception:
        return 0.0

def calcular_dias_para_anular_il(il_usd, fees_dia_media):
    if fees_dia_media <= 0 or il_usd <= 0:
        return 0.0
    return il_usd / fees_dia_media

def sincronizar_pools_silencioso(pools_lista):
    agora = time.time()
    for p in pools_lista:
        if normalizar_estado(p.get("estado")) == "Fechada":
            continue
            
        addr = p.get("wallet_address")
        par_nome = p.get("par", "Par N/A")
        if addr:
            p_usd, p_nat = fetch_dexscreener_data(addr)
            if p_nat is not None:
                r_min = to_float(p.get("range_min"))
                r_max = to_float(p.get("range_max"))
                estado_anterior = normalizar_estado(p.get("estado"))
                
                in_range = True
                if r_max > 0 and p_nat > r_max:
                    in_range = False
                elif r_min > 0 and p_nat < r_min:
                    in_range = False
                
                novo_estado = "Ativa" if in_range else "Inativa"
                
                if estado_anterior == "Ativa" and novo_estado == "Inativa":
                    msg_alerta = (
                        f"🚨 <b>ALERTA DE SAÍDA DE RANGE!</b> 🚨\n\n"
                        f"📌 <b>Pool:</b> {par_nome}\n"
                        f"📉 <b>Preço Atual:</b> {format_crypto_price(p_nat)}\n"
                        f"🎯 <b>Range Definido:</b> {format_crypto_price(r_min)} - {format_crypto_price(r_max)}\n"
                        f"⚠️ A posição ficou <b>INATIVA</b>. Avalia se pretendes fazer re-range."
                    )
                    send_telegram(msg_alerta)
                elif novo_estado == "Ativa" and r_min > 0 and r_max > 0:
                    dist_inf_pct = ((p_nat - r_min) / r_min) * 100
                    dist_sup_pct = ((r_max - p_nat) / r_max) * 100
                    
                    if dist_inf_pct <= 3.0:
                        msg_prox = (
                            f"⚠️ <b>ALERTA DE PROXIMIDADE (LIMITE INFERIOR)</b>\n\n"
                            f"📌 <b>Pool:</b> {par_nome}\n"
                            f"📉 <b>Preço Atual:</b> {format_crypto_price(p_nat)}\n"
                            f"🔴 <b>Range Mínimo:</b> {format_crypto_price(r_min)} (A {dist_inf_pct:.2f}% do limite!)"
                        )
                        send_telegram(msg_prox)
                    elif dist_sup_pct <= 3.0:
                        msg_prox = (
                            f"⚠️ <b>ALERTA DE PROXIMIDADE (LIMITE SUPERIOR)</b>\n\n"
                            f"📌 <b>Pool:</b> {par_nome}\n"
                            f"📈 <b>Preço Atual:</b> {format_crypto_price(p_nat)}\n"
                            f"🔴 <b>Range Máximo:</b> {format_crypto_price(r_max)} (A {dist_sup_pct:.2f}% do limite!)"
                        )
                        send_telegram(msg_prox)

                p_ini = to_float(p.get("preco_inicial"))
                v_inv = to_float(p.get("valor_inicial"))
                v_at_db = to_float(p.get("valor_atual"))
                
                if p_ini > 0 and p_nat > 0 and v_inv > 0:
                    wa = calcular_peso_clmm(p_nat, r_min, r_max)
                    wb = 1.0 - wa
                    ratio = p_nat / p_ini
                    v_estimado = v_inv * ((wa * ratio) + wb)
                else:
                    v_estimado = v_at_db if v_at_db > 0 else v_inv

                patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{p['id']}"
                patch_data = {
                    "preco_nativo": p_nat,
                    "estado": novo_estado,
                    "valor_atual": round(v_estimado, 2),
                    "last_price_update": agora
                }
                if p_usd:
                    patch_data["preco_atual"] = p_usd
                    
                requests.patch(patch_url, headers=headers, json=patch_data)

# -----------------------------------------------------------------------------
# 4. CARREGAMENTO E AUTO-SYNC
# -----------------------------------------------------------------------------
pools = get_pools()
lista_aportes_raw = get_aportes()

mapa_aportes = {}
for a in lista_aportes_raw:
    pid = a.get("pool_id")
    v_ap = to_float(a.get("valor"))
    if pid is not None:
        mapa_aportes[pid] = mapa_aportes.get(pid, 0.0) + v_ap

if "last_auto_sync" not in st.session_state or (time.time() - st.session_state["last_auto_sync"] > 180):
    sincronizar_pools_silencioso(pools)
    st.session_state["last_auto_sync"] = time.time()
    pools = get_pools()

st.sidebar.title("⚡ DeFi Hub Pro")
filtro_estado = st.sidebar.selectbox("Filtrar Posições:", ["Apenas Abertas (Ativas/Fora)", "Ativas 🟢", "Fora de Range 🔴", "Todas"])

esconder_detalhes = st.sidebar.checkbox("👁️ Ocultar Detalhes das Pools", value=False)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Sincronizar Tudo", use_container_width=True):
    with st.spinner("A atualizar posições abertas..."):
        sincronizar_pools_silencioso(pools)
    st.sidebar.success("Sincronizado!")
    st.rerun()

if st.sidebar.button("🧪 Testar Alerta Telegram", use_container_width=True):
    test_msg = f"🧪 <b>TESTE DE CONEXÃO DEFI HUB PRO</b>\n\nNotificação enviada às {get_agora_pt().strftime('%H:%M:%S')} PT com sucesso!"
    if send_telegram(test_msg):
        st.sidebar.success("Alerta enviado para o Telegram!")
    else:
        st.sidebar.error("Erro ao enviar. Verifica o Bot Token e Chat ID.")

# -----------------------------------------------------------------------------
# 5. CÁLCULO DE MÉTRICAS COMPLETO
# -----------------------------------------------------------------------------
total_investido_inicial = 0.0
total_aportes_extra = 0.0
total_investido_global = 0.0
total_valor_atual = 0.0
total_fees_sacadas = 0.0
total_fees_sacadas_atual = 0.0
total_fees_por_recolher = 0.0
total_fees = 0.0
total_fees_diarias_corridas = 0.0
total_fees_diarias_ativas = 0.0
total_ativas = 0
total_inativas = 0

pools_processadas = []
pools_fechadas_processadas = []

for p in pools:
    pool_id = p.get("id")
    v_inv_inicial = to_float(p.get("valor_inicial"))
    v_aportes = mapa_aportes.get(pool_id, 0.0)
    v_inv_total = v_inv_inicial + v_aportes

    v_at = to_float(p.get("valor_atual"))
    v_fees_sacadas = to_float(p.get("fees"))
    v_fees_por_recolher = to_float(p.get("position_pubkey"))
    data_ent = p.get("data_entrada", "")
    data_fecho = p.get("data_fecho", None)
    hrs_inativa = to_float(p.get("horas_inativa"))
    estado = normalizar_estado(p.get("estado"))
    tipo_proto = identificar_tipo_protocolo(p.get("rede"))

    p_nat_atual = to_float(p.get("preco_nativo"))
    p_nat_inicial = to_float(p.get("preco_inicial"))
    r_min = to_float(p.get("range_min"))
    r_max = to_float(p.get("range_max"))

    wa_fees = calcular_peso_clmm(p_nat_atual, r_min, r_max)
    wb_fees = 1.0 - wa_fees
    ratio_preco_fees = (p_nat_atual / p_nat_inicial) if p_nat_inicial > 0 else 1.0

    if v_fees_sacadas > 0 and p_nat_inicial > 0 and p_nat_atual > 0:
        v_fees_sacadas_atual = v_fees_sacadas * ((wa_fees * ratio_preco_fees) + wb_fees)
    else:
        v_fees_sacadas_atual = v_fees_sacadas

    il_pct = calcular_il_clmm(p_nat_inicial, p_nat_atual, r_min, r_max)
    il_usd = abs(il_pct / 100.0) * v_inv_total
    custo_medio_inf = calcular_custo_medio_inferior_rigoroso(p_nat_inicial, r_min, r_max)

    v_fees_totais_pool = v_fees_sacadas_atual + v_fees_por_recolher
    v_atual_final = v_at if v_at > 0 else v_inv_total

    if estado == "Fechada":
        v_fecho_real = to_float(p.get("valor_fecho"), v_atual_final)
        pnl_pool = (v_fecho_real + v_fees_sacadas) - v_inv_total
    else:
        pnl_pool = (v_atual_final + v_fees_totais_pool) - v_inv_total

    roi_pool = (pnl_pool / v_inv_total * 100) if v_inv_total > 0 else 0.0

    dias_corridos, dias_ativos = calcular_dias_metricas(data_ent, hrs_inativa, data_fecho)
    
    fees_dia_corrido = v_fees_totais_pool / dias_corridos
    apr_corrido = ((v_fees_totais_pool / v_inv_total) / dias_corridos * 365 * 100) if v_inv_total > 0 else 0.0

    fees_dia_ativo = v_fees_totais_pool / dias_ativos
    apr_ativo = ((v_fees_totais_pool / v_inv_total) / dias_ativos * 365 * 100) if v_inv_total > 0 else 0.0

    eficiencia_1k = (fees_dia_corrido / v_inv_total * 1000) if v_inv_total > 0 else 0.0

    dias_cobertura = calcular_dias_para_anular_il(il_usd, fees_dia_corrido)

    p_item = p.copy()
    p_item["estado"] = estado
    p_item["tipo_proto"] = tipo_proto
    p_item["v_inicial_puro"] = v_inv_inicial
    p_item["v_aportes_calc"] = v_aportes
    p_item["v_inicial_calc"] = v_inv_total
    p_item["v_atual_calc"] = v_atual_final
    p_item["fees_sacadas_calc"] = v_fees_sacadas
    p_item["fees_sacadas_atual_calc"] = v_fees_sacadas_atual
    p_item["fees_por_recolher_calc"] = v_fees_por_recolher
    p_item["fees_calc"] = v_fees_totais_pool
    p_item["il_pct_calc"] = il_pct
    p_item["il_usd_calc"] = il_usd
    p_item["custo_medio_inf_calc"] = custo_medio_inf
    p_item["dias_cobertura_calc"] = dias_cobertura
    p_item["pnl_pool"] = pnl_pool
    p_item["roi_pool"] = roi_pool
    p_item["dias_corridos"] = dias_corridos
    p_item["dias_ativos"] = dias_ativos
    p_item["fees_dia_corrido"] = fees_dia_corrido
    p_item["apr_corrido"] = apr_corrido
    p_item["eficiencia_1k"] = eficiencia_1k

    if estado == "Fechada":
        pools_fechadas_processadas.append(p_item)
    else:
        total_investido_inicial += v_inv_inicial
        total_aportes_extra += v_aportes
        total_investido_global += v_inv_total
        total_valor_atual += v_atual_final
        total_fees_sacadas += v_fees_sacadas
        total_fees_sacadas_atual += v_fees_sacadas_atual
        total_fees_por_recolher += v_fees_por_recolher
        total_fees += v_fees_totais_pool
        total_fees_diarias_corridas += fees_dia_corrido
        total_fees_diarias_ativas += fees_dia_ativo

        if estado == "Ativa":
            total_ativas += 1
        else:
            total_inativas += 1

        pools_processadas.append(p_item)

valor_nas_pools = total_valor_atual + total_fees_por_recolher
valor_total_com_fees = total_valor_atual + total_fees
pnl_global = valor_total_com_fees - total_investido_global
roi_global = (pnl_global / total_investido_global * 100) if total_investido_global > 0 else 0.0

hoje_str = get_agora_pt().strftime('%Y-%m-%d')
hist_pnl_data = get_historico_pnl()
dif_dia_anterior = 0.0
pct_dia_anterior = 0.0
delta_delta_val = None

if hist_pnl_data:
    registos_anteriores = [r for r in hist_pnl_data if str(r.get("data")) < hoje_str]
    if registos_anteriores:
        ultimo_registo = registos_anteriores[-1]
        valor_anterior = to_float(ultimo_registo.get("valor_total_usd"))
        if valor_anterior > 0:
            dif_dia_anterior = valor_nas_pools - valor_anterior
            pct_dia_anterior = (dif_dia_anterior / valor_anterior) * 100
            delta_delta_val = round(dif_dia_anterior, 2)

if st.sidebar.button("📸 Guardar Snapshot Diário", use_container_width=True):
    payload_pnl = {
        "data": hoje_str,
        "valor_total_usd": round(valor_nas_pools, 2)
    }
    res = requests.post(f"{SUPABASE_URL}/rest/v1/historico_pnl", headers=headers, json=payload_pnl)
    if res.status_code in [200, 201]:
        st.sidebar.success(f"Snapshot de {hoje_str} (${valor_nas_pools:,.2f}) guardado!")
        time.sleep(1)
        st.rerun()
    else:
        st.sidebar.error("Erro ao guardar snapshot no Supabase.")

if st.sidebar.button("📲 Resumo no Telegram", use_container_width=True):
    msg_resumo = (
        f"📊 <b>PORTFÓLIO DEFI ({get_agora_pt().strftime('%d/%m/%Y %H:%M')} PT)</b>\n\n"
        f"💰 <b>Investido Total:</b> ${total_investido_global:,.2f} (${total_aportes_extra:,.2f} aportes)\n"
        f"💵 <b>Atual nas Pools:</b> ${valor_nas_pools:,.2f}\n"
        f"💸 <b>Fees Totais:</b> ${total_fees:,.2f} (${total_fees_sacadas_atual:,.2f} val. atual)\n"
        f"📈 <b>PnL:</b> ${pnl_global:,.2f} ({roi_global:.2f}%)\n"
        f"📌 <b>Ativas:</b> 🟢 {total_ativas} | 🔴 {total_inativas}"
    )
    if send_telegram(msg_resumo):
        st.sidebar.success("Enviado!")

if st.sidebar.button("📈 Enviar Relatório Semanal", use_container_width=True):
    msg_semanal = (
        f"📋 <b>RELATÓRIO SEMANAL DEFI HUB PRO</b>\n"
        f"📅 <i>Data: {get_agora_pt().strftime('%d/%m/%Y')}</i>\n\n"
        f"💰 <b>Capital Investido:</b> ${total_investido_global:,.2f}\n"
        f"💵 <b>Valor Atual em Pools:</b> ${valor_nas_pools:,.2f}\n"
        f"💸 <b>Fees Totais Geradas:</b> ${total_fees:,.2f}\n"
        f"📈 <b>PnL Global:</b> ${pnl_global:,.2f} ({roi_global:.2f}%)\n\n"
        f"🟢 <b>Pools Ativas:</b> {total_ativas}\n"
        f"🔴 <b>Pools Fora de Range:</b> {total_inativas}\n"
        f"🏆 <b>Pools Fechadas:</b> {len(pools_fechadas_processadas)}"
    )
    if send_telegram(msg_semanal):
        st.sidebar.success("Relatório semanal enviado!")
    else:
        st.sidebar.error("Erro ao enviar relatório.")

# -----------------------------------------------------------------------------
# 6. EXIBIÇÃO DE KPIS
# -----------------------------------------------------------------------------
st.title("⚡ Liquidity Hub Pro")

k1, k2, k3 = st.columns(3)
k1.metric("Capital Total Investido", f"${total_investido_global:,.2f}", delta=f"+${total_aportes_extra:,.2f} em aportes")

if delta_delta_val is not None:
    k2.metric("Valor em Pools", f"${valor_nas_pools:,.2f}", delta=f"{delta_delta_val:+,.2f} ({pct_dia_anterior:+.2f}%) vs ontem")
else:
    k2.metric("Valor em Pools", f"${valor_nas_pools:,.2f}", delta="Sem histórico anterior")

k3.metric("Fees Totais 💸", f"${total_fees:,.2f}", delta=f"${total_fees_sacadas_atual:,.2f} val. atual")

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
    st.info("Nenhuma piscina ativa encontrada com o filtro selecionado.")
else:
    for p in pools_filtradas:
        pool_id = p["id"]
        par = p.get("par", "Par N/A")
        rede = p.get("rede", "DeFi")
        tipo_proto = p["tipo_proto"]
        estado = p.get("estado", "Ativa")
        p_nat = to_float(p.get("preco_nativo"))
        p_usd = to_float(p.get("preco_atual"))
        r_min = to_float(p.get("range_min"))
        r_max = to_float(p.get("range_max"))
        
        v_inv_puro = p["v_inicial_puro"]
        v_aportes = p["v_aportes_calc"]
        v_inv_total = p["v_inicial_calc"]
        v_at = p["v_atual_calc"]
        v_fees_sacadas = p["fees_sacadas_calc"]
        v_fees_sacadas_atual = p["fees_sacadas_atual_calc"]
        v_fees_por_recolher = p["fees_por_recolher_calc"]
        v_fees_totais = p["fees_calc"]
        
        il_pct = p["il_pct_calc"]
        il_usd = p["il_usd_calc"]
        custo_medio_inf = p["custo_medio_inf_calc"]
        dias_cobertura = p["dias_cobertura_calc"]

        pnl_pool = p["pnl_pool"]
        roi_pool = p["roi_pool"]
        
        dias_corridos = p["dias_corridos"]
        fees_dia_corrido = p["fees_dia_corrido"]
        apr_corrido = p["apr_corrido"]
        eficiencia_1k = p["eficiencia_1k"]

        tipo_desvio = "EM RANGE"
        motivo_saida = ""
        is_abaixo_range = False
        if r_max > 0 and p_nat > r_max:
            pct = ((p_nat - r_max) / r_max) * 100
            tipo_desvio = f"+{pct:.2f}% (Acima)"
            motivo_saida = "⚠️ Saída pelo limite SUPERIOR."
        elif r_min > 0 and p_nat < r_min:
            pct = ((r_min - p_nat) / r_min) * 100
            tipo_desvio = f"-{pct:.2f}% (Abaixo)"
            is_abaixo_range = True
            motivo_saida = f"⚠️ Saída pelo limite INFERIOR (100% Volátil). Custo médio real de aquisição: {format_crypto_price(custo_medio_inf)}"

        if estado == "Ativa":
            badge_html = f'<span class="badge-active">🟢 EM RANGE ({tipo_proto})</span>'
            card_class = "pool-card pool-card-active"
        else:
            badge_html = f'<span class="badge-inactive">🔴 FORA ({tipo_desvio} | {tipo_proto})</span>'
            card_class = "pool-card pool-card-inactive"

        dif_valor = v_at - v_inv_total
        cor_dif = "#10b981" if dif_valor >= 0 else "#ef4444"
        sinal_dif = "+" if dif_valor > 0 else ""

        with st.container():
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <h3 style="margin:0;">{par} <span style="font-size: 0.9rem; color: #38bdf8;">({rede})</span> <span style="font-size: 0.8rem; color: #a0aec0;">({dias_corridos:.0f}d corridos)</span></h3>
                    {badge_html}
                </div>
                <div style="font-size: 0.9rem; color: #cbd5e1; display: flex; gap: 16px; border-top: 1px solid #2d3748; padding-top: 6px;">
                    <span>📥 <b>Inicial:</b> ${v_inv_puro:,.2f}</span>
                    <span>➕ <b>Aportes:</b> ${v_aportes:,.2f}</span>
                    <span>💵 <b>Atual:</b> ${v_at:,.2f}</span>
                    <span>📊 <b>Dif:</b> <span style="color: {cor_dif};">{sinal_dif}${dif_valor:,.2f}</span></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if not esconder_detalhes:
                c_p1, c_p2, c_p3, c_p4 = st.columns(4)
                c_p1.metric("Preço Nativo (Rácio)", format_crypto_price(p_nat), delta=f"${p_usd:.4f}" if p_usd > 0 else None)
                c_p2.metric("Range Definição", f"{format_crypto_price(r_min)} - {format_crypto_price(r_max)}")
                c_p3.metric("Rendimento Diário", f"${fees_dia_corrido:,.2f}/d", delta=f"{apr_corrido:.1f}% APR")
                c_p4.metric("Eficiência do Capital", f"${eficiencia_1k:,.2f} /dia", delta="Por cada $1.000")

                if motivo_saida and estado != "Ativa":
                    st.caption(motivo_saida)

                render_sparkline_chart(p_nat, r_min, r_max)

                c_p5, c_p6, c_p7, c_p8 = st.columns(4)
                c_p5.metric("Fees Sacadas", f"${v_fees_sacadas:,.2f}", delta=f"Atual: ${v_fees_sacadas_atual:,.2f}")
                c_p6.metric("Fees Por Recolher", f"${v_fees_por_recolher:,.2f}")
                c_p7.metric("Fees Totais", f"${v_fees_totais:,.2f}")
                c_p8.metric("PnL Total (+Fees)", f"${pnl_pool:,.2f}", delta=f"{roi_pool:.2f}%")

                col_actions1, col_actions2 = st.columns(2)
                
                with col_actions1:
                    with st.expander(f"💸 Registo Rápido de Saque — {par}"):
                        val_saque_hoje = st.number_input(
                            "Valor Total das Fees Sacadas ($ USD):", 
                            min_value=0.0, 
                            step=1.0, 
                            key=f"input_saque_{pool_id}"
                        )
                        
                        c_tok_a, c_tok_b = st.columns(2)
                        qtd_tok_a_input = c_tok_a.number_input(
                            "Qtd Token A (Volátil):", 
                            min_value=0.0, 
                            format="%.6f", 
                            key=f"input_qtd_a_{pool_id}"
                        )
                        qtd_tok_b_input = c_tok_b.number_input(
                            "Qtd Token B (Base/USDC):", 
                            min_value=0.0, 
                            format="%.4f", 
                            key=f"input_qtd_b_{pool_id}"
                        )
                        
                        data_saque_hoje = st.date_input(
                            "Data do Saque:", 
                            value=get_agora_pt().date(), 
                            key=f"input_data_saque_{pool_id}"
                        )
                        
                        if st.button("⚡ Registar Saque", key=f"btn_saque_{pool_id}", use_container_width=True):
                            if val_saque_hoje > 0:
                                novas_fees_sacadas = v_fees_sacadas + val_saque_hoje
                                patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
                                res_pool = requests.patch(patch_url, headers=headers, json={"fees": novas_fees_sacadas})
                                
                                if qtd_tok_a_input == 0 and qtd_tok_b_input == 0:
                                    wa_saque = calcular_peso_clmm(p_nat, r_min, r_max)
                                    wb_saque = 1.0 - wa_saque
                                    val_usd_token_a = val_saque_hoje * wa_saque
                                    val_usd_token_b = val_saque_hoje * wb_saque
                                    p_usd_a = p_usd if p_usd > 0 else (p_nat if p_nat > 0 else 1.0)
                                    final_qtd_a = val_usd_token_a / p_usd_a if p_usd_a > 0 else 0.0
                                    final_qtd_b = val_usd_token_b
                                else:
                                    final_qtd_a = qtd_tok_a_input
                                    final_qtd_b = qtd_tok_b_input
                                
                                payload_historico = {
                                    "data": str(data_saque_hoje),
                                    "pool_id": pool_id,
                                    "par": par,
                                    "valor_usd": round(val_saque_hoje, 2),
                                    "qtd_token_a": round(final_qtd_a, 6),
                                    "qtd_token_b": round(final_qtd_b, 4)
                                }
                                res_hist = requests.post(f"{SUPABASE_URL}/rest/v1/historico_fees", headers=headers, json=payload_historico)

                                if res_pool.status_code in [200, 204] and res_hist.status_code in [200, 201]:
                                    st.success(f"Registadas +${val_saque_hoje:,.2f} em fees!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Erro ao atualizar o Supabase.")

                with col_actions2:
                    with st.expander(f"➕ Registar Aporte / Reinvestimento — {par}"):
                        val_aporte_hoje = st.number_input(
                            "Valor do Aporte ($ USD):", 
                            min_value=0.0, 
                            step=5.0, 
                            key=f"input_aporte_{pool_id}"
                        )
                        data_aporte_hoje = st.date_input(
                            "Data do Aporte:", 
                            value=get_agora_pt().date(), 
                            key=f"input_data_aporte_{pool_id}"
                        )
                        
                        if st.button("➕ Registar Aporte", key=f"btn_aporte_{pool_id}", use_container_width=True):
                            if val_aporte_hoje > 0:
                                payload_aporte = {
                                    "pool_id": pool_id,
                                    "valor": round(val_aporte_hoje, 2),
                                    "data_aporte": str(data_aporte_hoje)
                                }
                                res_ap = requests.post(f"{SUPABASE_URL}/rest/v1/aportes", headers=headers, json=payload_aporte)

                                if res_ap.status_code in [200, 201]:
                                    st.success(f"Aporte de +${val_aporte_hoje:,.2f} registado com sucesso!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Erro ao registar aporte: {res_ap.text}")

            st.markdown("---")

# -----------------------------------------------------------------------------
# 8. GRÁFICOS DE ANÁLISE DO PORTFÓLIO (ATIVAS)
# -----------------------------------------------------------------------------
st.subheader("📊 Análise do Portfólio (Ativas)")
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
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)", 
            font_color="white", 
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig_pie, use_container_width=True)

with col_g2:
    hist_data = get_historico_pnl()
    if hist_data:
        df_hist = pd.DataFrame(hist_data)
        fig_hist = px.area(
            df_hist, 
            x="data", 
            y="valor_total_usd", 
            title="Evolução do Valor Total nas Pools ($ USD)",
            markers=True
        )
        fig_hist.update_traces(line_color="#10b981", fillcolor="rgba(16, 185, 129, 0.1)")
        fig_hist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)", 
            font_color="white", 
            margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("A aguardar histórico de PnL...")

if pools_processadas:
    df_active_perf = pd.DataFrame(pools_processadas)
    fig_active_perf = px.bar(
        df_active_perf,
        x="par",
        y="pnl_pool",
        color="pnl_pool",
        color_continuous_scale=["#ef4444", "#10b981"],
        title="Performance Individual (PnL Total + Fees) das Pools Ativas ($ USD)",
        text=df_active_perf["pnl_pool"].apply(lambda x: f"${x:,.2f}")
    )
    fig_active_perf.update_traces(textposition="outside")
    fig_active_perf.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_title="Par / Pool",
        yaxis_title="PnL ($ USD)",
        coloraxis_showscale=False
    )
    st.plotly_chart(fig_active_perf, use_container_width=True)

# -----------------------------------------------------------------------------
# 9. RAIO-X DETALHADO POR POOL
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🔍 Raio-X Detalhado por Pool (Histórico de Saques de Fees)")

todas_pools_combinadas = pools_processadas + pools_fechadas_processadas
if todas_pools_combinadas:
    mapa_selecao_pools = {f"ID {p['id']} - {p.get('par')} ({p.get('estado')})": p for p in todas_pools_combinadas}
    
    c_rx1, c_rx2, c_rx3 = st.columns(3)
    pool_escolhida_str = c_rx1.selectbox("Selecione uma pool:", list(mapa_selecao_pools.keys()))
    pool_raiox = mapa_selecao_pools[pool_escolhida_str]
    
    dt_inicio = c_rx2.date_input("Data Inicial:", value=date(2025, 1, 1), key="rx_dt_ini")
    dt_fim = c_rx3.date_input("Data Final:", value=get_agora_pt().date(), key="rx_dt_fim")
    
    fees_hist_raw = get_historico_fees()
    fees_pool_filtradas = []
    
    for f in fees_hist_raw:
        if f.get("pool_id") == pool_raiox["id"]:
            data_f_str = str(f.get("data", "")).strip()
            try:
                dt_f = datetime.strptime(data_f_str, "%Y-%m-%d").date()
                if dt_inicio <= dt_f <= dt_fim:
                    fees_pool_filtradas.append(f)
            except Exception:
                fees_pool_filtradas.append(f)
    
    if fees_pool_filtradas:
        df_fees_raiox = pd.DataFrame(fees_pool_filtradas)
        fig_raiox = px.bar(
            df_fees_raiox,
            x="data",
            y="valor_usd",
            title=f"Histórico de Saques de Fees — {pool_raiox.get('par')} ({dt_inicio.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')})",
            text=df_fees_raiox["valor_usd"].apply(lambda x: f"${x:,.2f}"),
            color="valor_usd",
            color_continuous_scale=["#38bdf8", "#10b981"]
        )
        fig_raiox.update_traces(textposition="outside")
        fig_raiox.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="white",
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis_title="Data do Saque",
            yaxis_title="Valor Sacado ($ USD)",
            coloraxis_showscale=False
        )
        st.plotly_chart(fig_raiox, use_container_width=True)

        csv_data = df_fees_raiox.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"📥 Exportar Saques de {pool_raiox.get('par')} para CSV",
            data=csv_data,
            file_name=f"saques_fees_pool_{pool_raiox['id']}_{dt_inicio}_a_{dt_fim}.csv",
            mime="text/csv",
            use_container_width=False
        )
    else:
        st.info(f"Nenhum saque de fees encontrado para a pool {pool_raiox.get('par')} no período selecionado.")
else:
    st.info("Nenhuma pool disponível para análise.")

# -----------------------------------------------------------------------------
# 10. FERRAMENTAS & GESTÃO DE POOLS (Âncora para o botão de baixo)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown('<div id="ferramentas-gestao"></div>', unsafe_allow_html=True)
st.subheader("🛠️ Ferramentas & Gestão")

tab_add, tab_edit, tab_closed, tab_calc, tab_table, tab_fees_hist, tab_tokens_summary, tab_aportes_hist, tab_llama = st.tabs([
    "➕ Adicionar Pool", 
    "✏ Editar / Fechar Posição", 
    "🏆 Posições Fechadas",
    "🧮 Calculadora & IL", 
    "📄 Tabela Geral",
    "📜 Histórico de Fees",
    "📊 Resumo por Token",
    "➕ Histórico de Aportes",
    "🔥 DefiLlama Yields"
])

with tab_add:
    with st.form("form_add_pool"):
        c1, c2, c3 = st.columns(3)
        par_in = c1.text_input("Par (ex: SOL/USDC)", "")
        addr_in = c2.text_input("Pair Address (DexScreener)", "")
        rede_in = c3.text_input("Rede / Plataforma (ex: Raydium - CLMM / Meteora - DLMM)", "Raydium - CLMM")

        c4, c5, c6 = st.columns(3)
        invest_in = c4.number_input("Investimento Inicial ($ USD)", min_value=0.0, step=10.0)
        p_nat_inicial_in = c5.number_input("Preço Nativo Inicial (Rácio)", min_value=0.0, format="%.8f")
        v_atual_in = c6.number_input("Valor Atual Posição ($ USD)", min_value=0.0, step=10.0)

        c7, c8, c9 = st.columns(3)
        rmin_in = c7.number_input("Range Mínimo", min_value=0.0, format="%.8f")
        rmax_in = c8.number_input("Range Máximo", min_value=0.0, format="%.8f")
        data_ent_in = c9.text_input("Data Entrada (YYYY-MM-DD)", value=get_agora_pt().strftime('%Y-%m-%d'))
        
        c10, c11 = st.columns(2)
        fees_sacadas_in = c10.number_input("Fees Já Sacadas ($ USD)", min_value=0.0, step=1.0)
        fees_por_recolher_in = c11.number_input("Fees Por Recolher ($ USD)", min_value=0.0, step=1.0)

        btn_save = st.form_submit_button("Salvar Nova Pool")

        if btn_save:
            if not par_in or not addr_in:
                st.warning("Preencha o nome do par e a morada.")
            else:
                p_usd, p_nat = fetch_dexscreener_data(addr_in)
                payload = {
                    "par": par_in,
                    "wallet_address": addr_in,
                    "rede": rede_in,
                    "valor_inicial": invest_in,
                    "valor_atual": v_atual_in if v_atual_in > 0 else invest_in,
                    "fees": fees_sacadas_in,
                    "position_pubkey": str(fees_por_recolher_in),
                    "data_entrada": data_ent_in,
                    "preco_inicial": p_nat_inicial_in if p_nat_inicial_in > 0 else (p_nat or 0),
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
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Erro ao salvar: {res.text}")

with tab_edit:
    if not pools:
        st.info("Não existem pools para editar.")
    else:
        lista_opcoes = {f"ID {p['id']} - {p.get('par', 'N/A')} ({p.get('rede', '')})": p for p in pools}
        escolha = st.selectbox("Selecione a Pool a Editar:", list(lista_opcoes.keys()))
        pool_sel = lista_opcoes[escolha]
        
        with st.form("form_edit_pool"):
            st.markdown(f"**Editar Posição ID {pool_sel['id']} ({pool_sel.get('par')})**")

            e_rede = st.text_input("Rede / Plataforma", value=str(pool_sel.get("rede", "")))

            e1, e2, e_inv = st.columns(3)
            e_val_atual = e1.number_input("Valor Atual Posição ($)", value=to_float(pool_sel.get("valor_atual")), step=10.0)
            e_pnat_inicial = e2.number_input("Preço Nativo Inicial", value=to_float(pool_sel.get("preco_inicial")), format="%.8f")
            e_val_inicial = e_inv.number_input("Investimento Inicial Puro ($)", value=to_float(pool_sel.get("valor_inicial")), step=10.0)

            e3, e4, e5 = st.columns(3)
            e_fees_sacadas = e3.number_input("Fees Já Sacadas ($)", value=to_float(pool_sel.get("fees")), step=1.0)
            e_fees_por_recolher = e4.number_input("Fees Por Recolher ($)", value=to_float(pool_sel.get("position_pubkey")), step=1.0)
            e_data_ent = e5.text_input("Data Entrada", value=str(pool_sel.get("data_entrada", "")))

            e6, e7 = st.columns(2)
            e_rmin = e6.number_input("Range Mínimo", value=to_float(pool_sel.get("range_min")), format="%.8f")
            e_rmax = e7.number_input("Range Máximo", value=to_float(pool_sel.get("range_max")), format="%.8f")

            btn_update = st.form_submit_button("💾 Guardar Alterações")

            if btn_update:
                patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_sel['id']}"
                update_payload = {
                    "rede": e_rede,
                    "valor_atual": e_val_atual,
                    "preco_inicial": e_pnat_inicial,
                    "valor_inicial": e_val_inicial,
                    "fees": e_fees_sacadas,
                    "position_pubkey": str(e_fees_por_recolher),
                    "data_entrada": e_data_ent,
                    "range_min": e_rmin,
                    "range_max": e_rmax
                }
                res = requests.patch(patch_url, headers=headers, json=update_payload)
                if res.status_code in [200, 204]:
                    st.success("Alterações guardadas!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Erro ao guardar: {res.text}")

        st.markdown("---")
        
        st.markdown("#### 🏁 Encerrar / Arquivar Posição")
        with st.form("form_close_pool"):
            val_fecho_input = st.number_input("Valor Total Sacado ao Fechar ($ USD):", min_value=0.0, value=to_float(pool_sel.get("valor_atual")), step=10.0)
            data_fecho_input = st.date_input("Data de Fecho:", value=get_agora_pt().date())
            btn_close_action = st.form_submit_button("🔒 Confirmar e Arquivar Posição")

            if btn_close_action:
                patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_sel['id']}"
                close_payload = {
                    "estado": "Fechada",
                    "valor_fecho": val_fecho_input,
                    "data_fecho": str(data_fecho_input)
                }
                res_c = requests.patch(patch_url, headers=headers, json=close_payload)
                if res_c.status_code in [200, 204]:
                    st.success(f"Posição ID {pool_sel['id']} encerrada e movida para o histórico!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Erro ao fechar posição: {res_c.text}")

        st.markdown("---")
        st.markdown("#### 🚨 Eliminar Posição")
        if st.button(f"🗑️ Eliminar Permanente ID {pool_sel['id']}", type="primary", use_container_width=True):
            del_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_sel['id']}"
            del_res = requests.delete(del_url, headers=headers)
            if del_res.status_code in [200, 204]:
                st.success("Pool eliminada!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Erro ao eliminar a pool.")

with tab_closed:
    st.markdown("#### 🏆 Histórico de Posições Fechadas (PnL Realizado)")
    if pools_fechadas_processadas:
        total_pnl_fechado = sum(p["pnl_pool"] for p in pools_fechadas_processadas)
        total_pools_fechadas = len(pools_fechadas_processadas)
        winning_pools = sum(1 for p in pools_fechadas_processadas if p["pnl_pool"] > 0)
        win_rate = (winning_pools / total_pools_fechadas * 100) if total_pools_fechadas > 0 else 0.0
        duracao_media = sum(p["dias_corridos"] for p in pools_fechadas_processadas) / total_pools_fechadas

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("PnL Realizado Total", f"${total_pnl_fechado:,.2f}")
        mc2.metric("Win Rate", f"{win_rate:.1f}%", delta=f"{winning_pools}/{total_pools_fechadas} Lucrativas")
        mc3.metric("Total Pools Fechadas", f"{total_pools_fechadas}")
        mc4.metric("Duração Média", f"{duracao_media:.1f} dias")

        st.markdown("<br>", unsafe_allow_html=True)

        df_closed_perf = pd.DataFrame(pools_fechadas_processadas)
        fig_closed_perf = px.bar(
            df_closed_perf,
            x="par",
            y="pnl_pool",
            color="pnl_pool",
            color_continuous_scale=["#ef4444", "#10b981"],
            title="Performance Individual (PnL Realizado) das Pools Fechadas ($ USD)",
            text=df_closed_perf["pnl_pool"].apply(lambda x: f"${x:,.2f}")
        )
        fig_closed_perf.update_traces(textposition="outside")
        fig_closed_perf.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="white",
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis_title="Par / Pool",
            yaxis_title="PnL Realizado ($ USD)",
            coloraxis_showscale=False
        )
        st.plotly_chart(fig_closed_perf, use_container_width=True)

        st.markdown("---")

        df_closed = pd.DataFrame(pools_fechadas_processadas)
        cols_closed_display = {
            "id": "ID",
            "par": "Par",
            "rede": "Rede / Plataforma",
            "v_inicial_calc": "Capital Investido ($)",
            "fees_sacadas_calc": "Fees Sacadas ($)",
            "pnl_pool": "PnL Realizado ($)",
            "roi_pool": "ROI Realizado (%)",
            "dias_corridos": "Duração (Dias)"
        }
        
        existing_cols = [c for c in cols_closed_display.keys() if c in df_closed.columns]
        df_closed_show = df_closed[existing_cols].rename(columns=cols_closed_display)
        
        for col in ["Capital Investido ($)", "Fees Sacadas ($)", "PnL Realizado ($)"]:
            if col in df_closed_show.columns:
                df_closed_show[col] = df_closed_show[col].apply(lambda x: f"${x:,.2f}")
        
        if "ROI Realizado (%)" in df_closed_show.columns:
            df_closed_show["ROI Realizado (%)"] = df_closed_show["ROI Realizado (%)"].apply(lambda x: f"{x:.2f}%")
            
        st.dataframe(df_closed_show, use_container_width=True, hide_index=True)
    else:
        st.info("Ainda não existem posições arquivadas como 'Fechadas'.")

with tab_calc:
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("#### 🎯 Calculadora de Novos Ranges")
        p_ref = st.number_input("Preço Nativo Atual", min_value=0.0, value=0.000049, format="%.8f", key="calc_p_ref")
        var_pct = st.slider("Amplitude (± %)", min_value=1.0, max_value=50.0, value=15.0, step=0.5, key="calc_var_pct")

        if p_ref > 0:
            novo_min = p_ref * (1 - (var_pct / 100))
            novo_max = p_ref * (1 + (var_pct / 100))
            st.write(f"**Novo Range Mínimo (-{var_pct}%):** `{format_crypto_price(novo_min)}`")
            st.write(f"**Novo Range Máximo (+{var_pct}%):** `{format_crypto_price(novo_max)}`")

    with col_c2:
        st.markdown("#### 📉 Simulador de IL CLMM / DLMM")
        var_preco_simulada = st.slider("Variação de Preço (%)", min_value=-80.0, max_value=300.0, value=20.0, step=5.0, key="calc_il_slider")
        rmin_sim = st.number_input("Range Mínimo (Simulação)", value=0.000030, format="%.8f")
        rmax_sim = st.number_input("Range Máximo (Simulação)", value=0.000080, format="%.8f")
        p_atual_sim = 0.000050 * (1.0 + var_preco_simulada / 100.0)

        wa_sim = calcular_peso_clmm(p_atual_sim, rmin_sim, rmax_sim)
        wb_sim = 1.0 - wa_sim
        razao_sim = 1.0 + (var_preco_simulada / 100.0)
        
        if wa_sim == 1.0:
            il_res = (razao_sim - 1) * 100
        elif wa_sim == 0.0:
            il_res = 0.0
        else:
            v_h = (wa_sim * razao_sim) + wb_sim
            v_l = razao_sim ** wa_sim
            il_res = ((v_l / v_h) - 1) * 100 if v_h > 0 else 0.0

        st.metric("IL Estimada", f"{il_res:.2f}%", delta=f"Peso Token A: {wa_sim*100:.1f}%", delta_color="inverse")

with tab_table:
    if pools_processadas:
        df_table = pd.DataFrame(pools_processadas)
        
        cols_display = {
            "id": "ID",
            "par": "Par",
            "rede": "Rede / Plataforma",
            "estado": "Estado",
            "v_inicial_puro": "Invest. Inicial ($)",
            "v_aportes_calc": "Aportes ($)",
            "v_inicial_calc": "Capital Total ($)",
            "v_atual_calc": "Valor Atual ($)",
            "eficiencia_1k": "Eficiência ($/dia por $1k)",
            "il_pct_calc": "IL (%)",
            "custo_medio_inf_calc": "Custo Médio Real (Queda)",
            "fees_sacadas_calc": "Fees Sacadas ($)",
            "fees_sacadas_atual_calc": "Fees Sacadas (Atual $)",
            "fees_por_recolher_calc": "Fees Por Recolher ($)",
            "fees_calc": "Fees Totais ($)",
            "pnl_pool": "Ganhos / Perdas ($ USD)",
            "roi_pool": "ROI (%)"
        }
        
        existing_cols = [c for c in cols_display.keys() if c in df_table.columns]
        df_display = df_table[existing_cols].rename(columns=cols_display)
        
        for col in ["Invest. Inicial ($)", "Aportes ($)", "Capital Total ($)", "Valor Atual ($)", "Fees Sacadas ($)", "Fees Sacadas (Atual $)", "Fees Por Recolher ($)", "Fees Totais ($)", "Ganhos / Perdas ($ USD)"]:
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(lambda x: f"${x:,.2f}")
        
        if "Eficiência ($/dia por $1k)" in df_display.columns:
            df_display["Eficiência ($/dia por $1k)"] = df_display["Eficiência ($/dia por $1k)"].apply(lambda x: f"${x:,.2f}")
        if "IL (%)" in df_display.columns:
            df_display["IL (%)"] = df_display["IL (%)"].apply(lambda x: f"{x:.2f}%")
        if "Custo Médio Real (Queda)" in df_display.columns:
            df_display["Custo Médio Real (Queda)"] = df_display["Custo Médio Real (Queda)"].apply(lambda x: format_crypto_price(x))
        if "ROI (%)" in df_display.columns:
            df_display["ROI (%)"] = df_display["ROI (%)"].apply(lambda x: f"{x:.2f}%")

        df_display = df_display.fillna("")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma posição ativa registada na base de dados.")

with tab_fees_hist:
    st.markdown("#### 📜 Registo Histórico de Saques de Fees")
    fees_hist_data = get_historico_fees()
    if fees_hist_data:
        df_fees_hist = pd.DataFrame(fees_hist_data)
        cols_hist = ["data", "par", "valor_usd"]
        if "qtd_token_a" in df_fees_hist.columns:
            cols_hist.append("qtd_token_a")
        if "qtd_token_b" in df_fees_hist.columns:
            cols_hist.append("qtd_token_b")
            
        df_fees_hist = df_fees_hist[cols_hist].rename(columns={
            "data": "Data do Saque",
            "par": "Par / Pool",
            "valor_usd": "Valor Sacado ($ USD)",
            "qtd_token_a": "Qtd Token Volátil",
            "qtd_token_b": "Qtd Token Base"
        })
        df_fees_hist["Valor Sacado ($ USD)"] = df_fees_hist["Valor Sacado ($ USD)"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_fees_hist, use_container_width=True, hide_index=True)
    else:
        st.info("Ainda não existem registos de saques de fees guardados.")

with tab_tokens_summary:
    st.markdown("#### 📊 Resumo de Tokens Sacados por Pool (Acumulado)")
    fees_hist_data = get_historico_fees()
    if fees_hist_data:
        df_summary = pd.DataFrame(fees_hist_data)
        
        df_summary["valor_usd"] = df_summary["valor_usd"].apply(to_float)
        df_summary["qtd_token_a"] = df_summary.get("qtd_token_a", 0).apply(to_float)
        df_summary["qtd_token_b"] = df_summary.get("qtd_token_b", 0).apply(to_float)
        
        grouped = df_summary.groupby("par").agg(
            total_saques=("id", "count"),
            total_usd=("valor_usd", "sum"),
            total_token_a=("qtd_token_a", "sum"),
            total_token_b=("qtd_token_b", "sum")
        ).reset_index()

        grouped_show = grouped.rename(columns={
            "par": "Par / Pool",
            "total_saques": "Nº de Saques",
            "total_token_a": "Total Token Volátil (A)",
            "total_token_b": "Total Token Base (B)",
            "total_usd": "Total Valor ($ USD)"
        })

        grouped_show["Total Valor ($ USD)"] = grouped_show["Total Valor ($ USD)"].apply(lambda x: f"${x:,.2f}")
        grouped_show["Total Token Volátil (A)"] = grouped_show["Total Token Volátil (A)"].apply(lambda x: f"{x:,.6f}")
        grouped_show["Total Token Base (B)"] = grouped_show["Total Token Base (B)"].apply(lambda x: f"{x:,.4f}")

        st.dataframe(grouped_show, use_container_width=True, hide_index=True)

        csv_summary = grouped.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Resumo de Tokens em CSV",
            data=csv_summary,
            file_name=f"resumo_tokens_sacados_{get_agora_pt().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("Nenhum histórico de fees disponível para gerar o resumo por token.")

with tab_aportes_hist:
    st.markdown("#### ➕ Registo Histórico de Aportes")
    if lista_aportes_raw:
        df_ap = pd.DataFrame(lista_aportes_raw)
        mapa_nomes_pools = {p["id"]: p.get("par", f"Pool ID {p['id']}") for p in pools}
        df_ap["par"] = df_ap["pool_id"].apply(lambda x: mapa_nomes_pools.get(x, f"Pool ID {x}"))
        
        df_ap_show = df_ap[["data_aporte", "par", "valor"]].rename(columns={
            "data_aporte": "Data do Aporte",
            "par": "Par / Pool",
            "valor": "Valor do Aporte ($ USD)"
        })
        df_ap_show["Valor do Aporte ($ USD)"] = df_ap_show["Valor do Aporte ($ USD)"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_ap_show, use_container_width=True, hide_index=True)
    else:
        st.info("Ainda não existem registos de aportes guardados.")

with tab_llama:
    st.markdown("#### 🦙 Maiores Rendimentos DeFi em Tempo Real (DefiLlama)")
    data_llama = fetch_defillama_yields()
    
    if not data_llama:
        st.warning("Não foi possível carregar os dados do DefiLlama de momento.")
    else:
        df_llama = pd.DataFrame(data_llama)
        col_f1, col_f2, col_f3 = st.columns(3)
        
        chains_disponiveis = sorted(df_llama["chain"].dropna().unique().tolist())
        default_chains = [c for c in ["Solana", "Ethereum", "Arbitrum"] if c in chains_disponiveis]
        chain_sel = col_f1.multiselect("Filtrar por Rede (Chain):", chains_disponiveis, default=default_chains)
        tvl_min = col_f2.number_input("TVL Mínimo ($ USD):", min_value=10000, value=100000, step=50000)
        ordem_sel = col_f3.selectbox("Ordenar por:", ["APY Total (apy)", "APY Base / Fees (apyBase)", "TVL ($)"])

        df_filtered = df_llama[df_llama["chain"].isin(chain_sel)] if chain_sel else df_llama
        df_filtered = df_filtered[df_filtered["tvlUsd"] >= tvl_min]

        sort_col = "apy"
        if ordem_sel == "APY Base / Fees (apyBase)":
            sort_col = "apyBase"
        elif ordem_sel == "TVL ($)":
            sort_col = "tvlUsd"

        df_filtered = df_filtered.sort_values(by=sort_col, ascending=False).head(50)
        
        df_filtered["link_llama"] = df_filtered.apply(lambda r: f"https://defillama.com/yields/pool/{r['pool']}", axis=1)
        
        cols_map = {
            "symbol": "Par / Símbolo",
            "project": "Protocolo",
            "chain": "Rede",
            "tvlUsd": "TVL ($)",
            "apy": "APY Total (%)",
            "link_llama": "DefiLlama"
        }
        
        df_show = df_filtered[list(cols_map.keys())].rename(columns=cols_map)
        df_show["TVL ($)"] = df_show["TVL ($)"].apply(lambda x: f"${x:,.0f}")
        df_show["APY Total (%)"] = df_show["APY Total (%)"].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "0.00%")

        st.dataframe(
            df_show, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "DefiLlama": st.column_config.LinkColumn("DefiLlama", display_text="🦙 Ver Pool")
            }
        )
