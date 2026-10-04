import datetime
import json
import time
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------
# CONEXÃO COM SUPABASE VIA REST API (PERSISTÊNCIA GARANTIDA)
# -------------------------------------------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -------------------------------------------------------------
# ALERTAS DO TELEGRAM
# -------------------------------------------------------------
def enviar_alerta_telegram(mensagem: str):
    """Envia alerta para o Telegram de forma segura."""
    token = st.secrets.get("TELEGRAM_TOKEN", "")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

def load_pools():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.warning("Configura os Secrets (SUPABASE_URL e SUPABASE_KEY) para ativar a persistência na nuvem.")
        return []

    url = f"{SUPABASE_URL}/rest/v1/pools?select=*&order=id.asc"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
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
                    "valor_inicial": float(r.get("valor_inicial", 0) or 0),
                    "valor_atual": float(r.get("valor_atual", 0) or 0),
                    "fees": float(r.get("fees", 0) or 0),
                    "range_min": float(r.get("range_min", 0) or 0),
                    "range_max": float(r.get("range_max", 0) or 0),
                    "data_entrada": dt_ent,
                    "wallet_address": str(r.get("wallet_address", "") or ""),
                    "preco_atual": float(r.get("preco_atual", 0.0) or 0.0),
                    "preco_nativo": float(r.get("preco_nativo", 0.0) or 0.0),
                    "horas_inativa": float(r.get("horas_inativa", 0.0) or 0.0),
                    "last_price_update": float(r.get("last_price_update", 0.0) or 0.0)
                })
            return pools
        else:
            st.error(f"Erro ao carregar do Supabase (Código {res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"Erro de conexão ao Supabase: {e}")
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
        "wallet_address": wallet_addr,
        "preco_atual": 0.0,
        "preco_nativo": 0.0,
        "horas_inativa": 0.0,
        "last_price_update": time.time()
    }
    try:
        res = requests.post(url, headers=HEADERS, json=payload, timeout=8)
        if res.status_code in [200, 201]:
            return True, "Pool adicionada com sucesso no Supabase!"
        else:
            return False, f"Erro {res.status_code}: {res.text}"
    except Exception as e:
        return False, f"Erro de conexão: {str(e)}"

def update_pool_db(pool_id, valor_atual, fees, data_entrada, valor_inicial=None, wallet_addr="", r_min=None, r_max=None, preco_atual=None, preco_nativo=None, estado=None, horas_inativa=None, last_update=None):
    url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
    payload = {
        "valor_atual": valor_atual,
        "fees": fees,
        "data_entrada": data_entrada.strftime("%Y-%m-%d"),
        "wallet_address": wallet_addr
    }
    if valor_inicial is not None:
        payload["valor_inicial"] = valor_inicial
    if r_min is not None and r_max is not None:
        payload["range_min"] = r_min
        payload["range_max"] = r_max
    if preco_atual is not None:
        payload["preco_atual"] = preco_atual
    if preco_nativo is not None:
        payload["preco_nativo"] = preco_nativo
    if estado is not None:
        payload["estado"] = estado
    if horas_inativa is not None:
        payload["horas_inativa"] = horas_inativa
    if last_update is not None:
        payload["last_price_update"] = last_update

    try:
        res = requests.patch(url, headers=HEADERS, json=payload, timeout=8)
        return res.status_code in [200, 204]
    except Exception:
        return False

def update_pool_status_db(pool_id, novo_estado):
    url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
    requests.patch(url, headers=HEADERS, json={"estado": novo_estado})

def delete_pool_db(pool_id):
    url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
    requests.delete(url, headers=HEADERS)

def clear_all_pools_db():
    url = f"{SUPABASE_URL}/rest/v1/pools?id=gt.0"
    requests.delete(url, headers=HEADERS)

# APORTES E SAQUES
def registrar_aporte_db(pool_id, valor_aporte, data_aporte):
    url_apt = f"{SUPABASE_URL}/rest/v1/aportes"
    payload = {
        "pool_id": pool_id,
        "valor": valor_aporte,
        "data_aporte": data_aporte.strftime("%Y-%m-%d")
    }
    requests.post(url_apt, headers=HEADERS, json=payload)

    pool = next((p for p in load_pools() if p["id"] == pool_id), None)
    if pool:
        n_v_init = pool["valor_inicial"] + valor_aporte
        url_p = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
        requests.patch(url_p, headers=HEADERS, json={"valor_inicial": n_v_init})

def get_historico_aportes(pool_id):
    url = f"{SUPABASE_URL}/rest/v1/aportes?pool_id=eq.{pool_id}&order=id.desc"
    try:
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            return [(r["id"], r["data_aporte"], r["valor"]) for r in res.json()]
    except Exception:
        pass
    return []

def delete_aporte_db(aporte_id, pool_id, valor_aporte):
    url_del = f"{SUPABASE_URL}/rest/v1/aportes?id=eq.{aporte_id}"
    requests.delete(url_del, headers=HEADERS)

    pool = next((p for p in load_pools() if p["id"] == pool_id), None)
    if pool:
        n_v_init = max(0.0, pool["valor_inicial"] - valor_aporte)
        url_p = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
        requests.patch(url_p, headers=HEADERS, json={"valor_inicial": n_v_init})

def registrar_saque_db(pool_id, valor_saque, data_saque):
    url_sq = f"{SUPABASE_URL}/rest/v1/saques"
    payload = {
        "pool_id": pool_id,
        "valor": valor_saque,
        "data_saque": data_saque.strftime("%Y-%m-%d")
    }
    requests.post(url_sq, headers=HEADERS, json=payload)

    pool = next((p for p in load_pools() if p["id"] == pool_id), None)
    if pool:
        n_fees = pool["fees"] + valor_saque
        url_p = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
        requests.patch(url_p, headers=HEADERS, json={"fees": n_fees})

def get_historico_saques(pool_id):
    url = f"{SUPABASE_URL}/rest/v1/saques?pool_id=eq.{pool_id}&order=id.desc"
    try:
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            return [(r["id"], r["data_saque"], r["valor"]) for r in res.json()]
    except Exception:
        pass
    return []

def delete_saque_db(saque_id, pool_id, valor_saque):
    url_del = f"{SUPABASE_URL}/rest/v1/saques?id=eq.{saque_id}"
    requests.delete(url_del, headers=HEADERS)

    pool = next((p for p in load_pools() if p["id"] == pool_id), None)
    if pool:
        n_fees = max(0.0, pool["fees"] - valor_saque)
        url_p = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{pool_id}"
        requests.patch(url_p, headers=HEADERS, json={"fees": n_fees})

# CONSULTA DE PREÇOS DEXSCREENER POR PAIR ADDRESS
def fetch_dexscreener_pair_price(pair_address):
    if not pair_address or not isinstance(pair_address, str):
        return None, None, None
    clean_addr = pair_address.strip()
    if not clean_addr:
        return None, None, None
    url = f"https://api.dexscreener.com/latest/dex/search?q={clean_addr}"
    try:
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data and "pairs" in data and len(data["pairs"]) > 0:
                pair = data["pairs"][0]
                price_usd = float(pair.get("priceUsd", 0))
                price_native = float(pair.get("priceNative", 0))
                return price_usd, price_native, "Ativa"
    except Exception:
        pass
    return None, None, None

# VERIFICAÇÃO AUTOMÁTICA DE PREÇOS E RANGE
def sync_pool_price_and_range(pool, force_sync=False):
    now = time.time()
    last_update = pool.get("last_price_update", 0.0)
    elapsed_hours = (now - last_update) / 3600.0 if last_update > 0 else 1.0

    if force_sync or elapsed_hours >= 1.0:
        p_usd, p_nat, _ = fetch_dexscreener_pair_price(pool.get("wallet_address", ""))
        
        if p_nat is not None and p_nat > 0:
            r_min = pool["range_min"]
            r_max = pool["range_max"]
            
            in_range = True
            if r_min > 0 and p_nat < r_min:
                in_range = False
                enviar_alerta_telegram(f"⚠️ *ALERTA (ABAIXO):* {pool['par']}\nPreço Nativo: `{p_nat}` | Mínimo: `{r_min}`")
            if r_max > 0 and p_nat > r_max:
                in_range = False
                enviar_alerta_telegram(f"⚠️ *ALERTA (ACIMA):* {pool['par']}\nPreço Nativo: `{p_nat}` | Máximo: `{r_max}`")
            
            novo_estado = "Ativa" if in_range else "Inativa"
            novas_horas_inativa = pool.get("horas_inativa", 0.0)
            
            if not in_range:
                novas_horas_inativa += elapsed_hours if last_update > 0 else 1.0

            update_pool_db(
                pool["id"], 
                valor_atual=pool["valor_atual"], 
                fees=pool["fees"], 
                data_entrada=pool["data_entrada"],
                wallet_addr=pool["wallet_address"],
                preco_atual=p_usd,
                preco_nativo=p_nat,
                estado=novo_estado,
                horas_inativa=novas_horas_inativa,
                last_update=now
            )
            return p_usd, p_nat, novo_estado
    return pool.get("preco_atual", 0.0), pool.get("preco_nativo", 0.0), pool.get("estado", "Ativa")

# ESTILOS CSS
st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; font-family: 'Inter', sans-serif; }
    .badge-ativa { background-color: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
    .badge-inativa { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
    .stButton > button { border-radius: 8px !important; font-weight: 500 !important; }
    [data-testid="stMetricValue"] { font-size: calc(1.0rem + 0.35vw) !important; line-height: 1.2 !important; white-space: nowrap !important; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem !important; white-space: nowrap !important; }
    </style>
""", unsafe_allow_html=True)

# HEADER
st.title("⚡ Gestor de Piscinas de Liquidez")
st.caption("Acompanhamento de performance e gestão DeFi (Persistência Cloud Activa)")

pools_data = load_pools()

for p in pools_data:
    sync_pool_price_and_range(p, force_sync=False)

DEX_OPTIONS = ["Raydium", "Uniswap v3", "Orca", "Kamino", "PancakeSwap", "Curve", "Meteora", "Cetus", "Outro"]

# MODAL RESUMO HISTÓRICO GERAL
@st.dialog("📋 Resumo Histórico das Piscinas")
def modal_tabela_resumo_historico():
    st.subheader("📋 Resumo Geral de Todas as Pools")
    st.caption("Estatísticas consolidadas de todas as posições.")
    if not pools_data:
        st.info("Nenhuma piscina encontrada no histórico.")
        return

    dt_hoje = datetime.date.today()
    resumo_rows = []

    for idx, p in enumerate(pools_data, start=1):
        dt_ent = p.get("data_entrada", dt_hoje)
        if isinstance(dt_ent, str):
            dt_ent = datetime.datetime.strptime(dt_ent, "%Y-%m-%d").date()

        dias = max(1, (dt_hoje - dt_ent).days)

        v_init = p["valor_inicial"]
        v_atual = p["valor_atual"]
        fees = p["fees"]
        pnl = (v_atual + fees) - v_init
        apr = (fees / v_init) * (365 / dias) * 100 if v_init > 0 else 0.0

        resumo_rows.append({
            "#": idx,
            "Par de Ativos": p["par"],
            "Plataforma / Rede": p["rede"],
            "Estado": p["estado"],
            "Preço Nativo": f"{p.get('preco_nativo', 0.0):.8f}",
            "Valor Inicial": f"${v_init:,.2f}",
            "Valor Atual": f"${v_atual:,.2f}",
            "Fees Acumuladas": f"${fees:,.2f}",
            "PnL Total": f"${pnl:+,.2f}",
            "APR Total (%)": f"{apr:.2f}%",
            "Data Entrada": dt_ent.strftime("%Y-%m-%d")
        })

    df_geral = pd.DataFrame(resumo_rows)
    st.dataframe(df_geral, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🗑️ Gerir / Eliminar Pools do Histórico")
    
    # Lista com ação individual de eliminação
    for p in pools_data:
        col_info, col_btn = st.columns([4, 1])
        with col_info:
            st.write(f"**ID {p['id']} - {p['par']}** ({p['rede']}) — Status: `{p['estado']}`")
        with col_btn:
            if st.button("🗑️️ Eliminar", key=f"del_hist_{p['id']}", type="primary", use_container_width=True):
                delete_pool_db(p["id"])
                st.toast(f"Pool #{p['id']} eliminada do Supabase!", icon="🗑️")
                time.sleep(0.5)
                st.rerun()

# MODAL DE SINCRONIZAÇÃO
@st.dialog("🔄 Sincronização On-Chain (DexScreener)")
def modal_sincronizar_carteira(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        p_usd, p_nat, _ = fetch_dexscreener_pair_price(pool.get("wallet_address", ""))
        
        if p_usd is None or p_usd == 0:
            p_usd = pool.get("preco_atual", 0.0)
            p_nat = pool.get("preco_nativo", 0.0)
            estado_range = pool.get("estado", "Ativa")
        else:
            r_min = pool.get("range_min", 0.0)
            r_max = pool.get("range_max", 0.0)
            in_range = True
            if r_min > 0 and p_nat < r_min:
                in_range = False
            if r_max > 0 and p_nat > r_max:
                in_range = False
            estado_range = "Ativa" if in_range else "Inativa"

        preco_ref = pool.get("preco_nativo", 0.0)
        valor_calculado = float(pool["valor_atual"])

        if p_nat and p_nat > 0 and preco_ref and preco_ref > 0:
            razao_preco = p_nat / preco_ref
            valor_calculado = round(pool["valor_atual"] * (razao_preco ** 0.5), 2)

        st.info(f"💡 Cotação Nativa no DexScreener: **{p_nat:.8f}** (${p_usd:.6f} USD) | Estado pelo Range: **{estado_range}**")

        novo_end = st.text_input("Morada do Par / Pair Address (DexScreener):", value=pool.get("wallet_address", ""), key=f"inp_addr_{pool_id}")
        v_manual = st.number_input("Valor Atual da Pool ($ USD) [Sugerido/Auto]:", min_value=0.0, value=float(valor_calculado), step=1.0, key=f"inp_val_{pool_id}")
        f_manual = st.number_input("Fees Acumuladas Totais ($ USD):", min_value=0.0, value=float(pool["fees"]), step=0.5, key=f"inp_fees_{pool_id}")
        
        col_r1, col_r2 = st.columns(2)
        r_min_modal = col_r1.number_input("Range Mín (Preço Nativo)", value=float(pool["range_min"]), format="%.8f", step=0.00000001, key=f"inp_rmin_{pool_id}")
        r_max_modal = col_r2.number_input("Range Máx (Preço Nativo)", value=float(pool["range_max"]), format="%.8f", step=0.00000001, key=f"inp_rmax_{pool_id}")

        st.markdown("---")
        
        if st.button("Sincronizar e Guardar", type="primary", use_container_width=True, key=f"btn_save_sync_{pool_id}"):
            dt_ent = pool.get("data_entrada", datetime.date.today())
            
            sucesso = update_pool_db(
                pool_id, 
                v_manual, 
                f_manual, 
                dt_ent, 
                wallet_addr=novo_end, 
                r_min=r_min_modal, 
                r_max=r_max_modal, 
                preco_atual=p_usd,
                preco_nativo=p_nat,
                estado=estado_range,
                last_update=time.time()
            )
            
            if sucesso:
                st.toast("✅ Dados guardados com sucesso!", icon="🎉")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Falha ao comunicar com o Supabase. Verifica os Secrets e a ligação.")

@st.dialog("➕ Gestão de Aportes")
def modal_gerir_aportes(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        tab_novo, tab_hist = st.tabs(["➕ Novo Aporte", "📋 Histórico de Aportes"])
        with tab_novo:
            with st.form(key=f"form_add_aporte_{pool_id}"):
                v_aporte = st.number_input("Valor do Aporte ($ USD):", min_value=0.01, value=100.0, step=10.0)
                dt_aporte = st.date_input("Data do Aporte:", datetime.date.today())
                if st.form_submit_button("Confirmar Aporte", type="primary", use_container_width=True):
                    registrar_aporte_db(pool_id, v_aporte, dt_aporte)
                    st.success("Aporte registado!")
                    st.rerun()
        with tab_hist:
            historico = get_historico_aportes(pool_id)
            total_aportado = sum(val for _, _, val in historico)
            st.metric("Total Aportado Nesta Pool", f"${total_aportado:,.2f}")
            st.markdown("---")
            if not historico:
                st.info("Nenhum aporte registado.")
            else:
                for apt_id, dt_str, val in historico:
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.write(f"📅 {dt_str}")
                    c2.write(f"💵 **${val:,.2f}**")
                    if c3.button("🗑️", key=f"del_apt_{apt_id}"):
                        delete_aporte_db(apt_id, pool_id, val)
                        st.rerun()

@st.dialog("💸 Gestão de Saques de Fees")
def modal_gerir_saques(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        tab_novo, tab_hist = st.tabs(["💸 Novo Saque", "📜 Histórico de Saques"])
        with tab_novo:
            with st.form(key=f"form_add_saque_{pool_id}"):
                v_saque = st.number_input("Valor do Saque ($ USD):", min_value=0.01, value=27.35, step=1.0)
                dt_saque = st.date_input("Data do Saque:", datetime.date.today())
                if st.form_submit_button("Confirmar Saque", type="primary", use_container_width=True):
                    registrar_saque_db(pool_id, v_saque, dt_saque)
                    st.success("Saque guardado!")
                    st.rerun()
        with tab_hist:
            historico = get_historico_saques(pool_id)
            if not historico:
                st.info("Nenhum saque registado.")
            else:
                for sq_id, dt_str, val in historico:
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.write(f"📅 {dt_str}")
                    c2.write(f"💸 **${val:,.2f}**")
                    if c3.button("🗑", key=f"del_sq_{sq_id}"):
                        delete_saque_db(sq_id, pool_id, val)
                        st.rerun()

@st.dialog("⚙ Editar Parâmetros")
def modal_atualizar_pool(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        with st.form(key=f"form_edit_modal_{pool_id}"):
            novo_v_init = st.number_input("Valor Inicial ($ USD)", min_value=0.0, value=float(pool["valor_inicial"]), step=10.0)
            novo_v_atual = st.number_input("Valor Atual ($ USD)", min_value=0.0, value=float(pool["valor_atual"]), step=10.0)
            novas_fees = st.number_input("Total Fees ($ USD)", min_value=0.0, value=float(pool["fees"]), step=0.5)
            end_c = st.text_input("Morada do Par (DexScreener)", value=pool.get("wallet_address", ""))
            col_r1, col_r2 = st.columns(2)
            novo_r_min = col_r1.number_input("Range Mín (Preço Nativo)", value=float(pool["range_min"]), format="%.8f", step=0.00000001)
            novo_r_max = col_r2.number_input("Range Máx (Preço Nativo)", value=float(pool["range_max"]), format="%.8f", step=0.00000001)
            nova_dt = st.date_input("Data Entrada", value=pool["data_entrada"])
            if st.form_submit_button("Guardar Alterações", type="primary", use_container_width=True):
                if update_pool_db(pool_id, novo_v_atual, novas_fees, nova_dt, valor_inicial=novo_v_init, wallet_addr=end_c, r_min=novo_r_min, r_max=novo_r_max):
                    st.success("Alterações salvas!")
                    st.rerun()

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
        wallet_addr = st.text_input("Morada do Par (DexScreener)")
        col_r1, col_r2 = st.columns(2)
        r_min = col_r1.number_input("Range Mín (Nativo)", format="%.8f", step=0.00000001)
        r_max = col_r2.number_input("Range Máx (Nativo)", format="%.8f", step=0.00000001)
        data_in = st.date_input("Data Entrada", datetime.date.today())

        if st.form_submit_button("Adicionar Pool", type="primary"):
            nome_par = par if par else "POOL/USD"
            nome_rede = f"{dex} - {rede if rede else 'Rede'}"
            v_actual_calc = v_atual if v_atual > 0 else v_init
            
            sucesso, msg = add_pool_db(
                nome_par, nome_rede, float(v_init), float(v_actual_calc), 
                float(fees_in), float(r_min), float(r_max), data_in, wallet_addr
            )
            
            if sucesso:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.markdown("---")
    if st.button("🗑 Limpar Portfólio"):
        clear_all_pools_db()
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
c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
c1.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
c2.metric("Total Fees Acumuladas", f"${total_fees:,.2f}")
c3.metric("APR Médio das Fees", f"{media_apr_fees:.2f}%")
with c4:
    if st.button("📊 Tabela Histórica Geral", use_container_width=True):
        modal_tabela_resumo_historico()

st.markdown("---")

if not pools_data:
    st.info("Nenhuma piscina registada.")
else:
    for idx, pool in enumerate(pools_data, start=1):
        dt_entrada = pool.get("data_entrada", datetime.date.today())
        dias_totais = max(1, (dt_hoje - dt_entrada).days)

        horas_inativa_totais = pool.get("horas_inativa", 0.0)
        dias_inativa = horas_inativa_totais / 24.0
        dias_ativa = max(0.0, dias_totais - dias_inativa)

        total_fees_geradas = pool["fees"]
        pnl_liquidez_usd = pool["valor_atual"] - pool["valor_inicial"]
        pnl_total_usd = (pool["valor_atual"] + total_fees_geradas) - pool["valor_inicial"]
        variacao_pct = ((pool["valor_atual"] - pool["valor_inicial"]) / pool["valor_inicial"]) * 100 if pool["valor_inicial"] > 0 else 0
        
        apr_fees = (total_fees_geradas / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0
        apr_liquidez = (pnl_liquidez_usd / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0
        apr_total = (pnl_total_usd / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0

        with st.container():
            head_col1, head_col2 = st.columns([1.5, 3.5])
            with head_col1:
                badge_class = "badge-ativa" if pool["estado"].lower() == "ativa" else "badge-inativa"
                p_nat_str = f" | Preço Nativo: {pool.get('preco_nativo', 0.0):.8f}" if pool.get('preco_nativo', 0.0) > 0 else ""
                st.markdown(f"### 🪙 **Pool #{idx}: {pool['par']}** <span class='{badge_class}'>{pool['estado']}</span>", unsafe_allow_html=True)
                st.caption(f"DEX / Rede: {pool['rede']} | Investido: ${pool['valor_inicial']:,.2f}{p_nat_str}")
                st.caption(f"⏱ **Tempo Ativa:** {dias_ativa:.1f} dias | **Tempo Inativa:** {dias_inativa:.1f} dias ({horas_inativa_totais:.0f}h)")

            with head_col2:
                m1, m2, m3, m4, m5 = st.columns([1, 1, 1, 1, 1])
                m1.metric("Valor Atual", f"${pool['valor_atual']:,.2f}")
                m2.metric("Variação", f"{variacao_pct:+.2f}%")
                m3.metric("PnL Total", f"${pnl_total_usd:+.2f}")
                m4.metric("APR Total", f"{apr_total:.2f}%")
                m5.metric("Fees", f"${pool['fees']:,.2f}")

            col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
            if col_b1.button("✏ Edit", key=f"edit_{pool['id']}", use_container_width=True):
                modal_atualizar_pool(pool["id"])

            if col_b2.button("🔗 Sincronizar", key=f"sync_{pool['id']}", use_container_width=True):
                modal_sincronizar_carteira(pool["id"])

            if col_b3.button("➕ Aporte", key=f"aporte_{pool['id']}", use_container_width=True):
                modal_gerir_aportes(pool["id"])

            if col_b4.button("💸 Sacar Fees", key=f"sacar_{pool['id']}", use_container_width=True):
                modal_gerir_saques(pool["id"])

            with col_b5:
                with st.popover("⚙️ Mais Opções", use_container_width=True):
                    if st.button("🔒 Alternar Estado", key=f"close_{pool['id']}", use_container_width=True):
                        update_pool_status_db(pool["id"], "Inativa" if pool["estado"] == "Ativa" else "Ativa")
                        st.rerun()
                    if st.button("🗑 Excluir Pool", key=f"del_{pool['id']}", use_container_width=True, type="primary"):
                        delete_pool_db(pool["id"])
                        st.rerun()

            show_chart_key = f"show_chart_{pool['id']}"
            if show_chart_key not in st.session_state:
                st.session_state[show_chart_key] = True

            chart_btn_col1, chart_btn_col2 = st.columns([3, 1])
            with chart_btn_col2:
                btn_label = "🙈 Esconder Gráficos" if st.session_state[show_chart_key] else "📈 Mostrar Gráficos"
                if st.button(btn_label, key=f"toggle_chart_{pool['id']}", use_container_width=True):
                    st.session_state[show_chart_key] = not st.session_state[show_chart_key]
                    st.rerun()

            if st.session_state[show_chart_key]:
                tab_il_vs_fees, tab_apr_perc = st.tabs([
                    "⚖️ Fees vs. Impermanent Loss / PnL ($)", 
                    "📊 Percentuais de APR (%)"
                ])

                full_dates = pd.date_range(start=dt_entrada, end=dt_hoje, freq="D")
                num_pontos = len(full_dates)

                if num_pontos == 1:
                    prog_fees = np.array([total_fees_geradas])
                    prog_pnl_liq = np.array([pnl_liquidez_usd])
                    sim_apr_fees = [apr_fees]
                    sim_apr_liq = [apr_liquidez]
                    sim_apr_tot = [apr_total]
                else:
                    dias_arr = np.arange(1, num_pontos + 1)
                    prog_fees = np.linspace(0.0, total_fees_geradas, num_pontos)

                    np.random.seed(pool["id"])
                    ruido = np.cumsum(np.random.normal(0, 1.5, size=num_pontos))
                    tendencia_val = np.linspace(pool["valor_inicial"], pool["valor_atual"], num_pontos)
                    prog_liq_val = tendencia_val + (ruido - ruido[0])
                    prog_liq_val[-1] = pool["valor_atual"]

                    prog_pnl_liq = prog_liq_val - pool["valor_inicial"]

                    sim_apr_fees = (prog_fees / pool["valor_inicial"]) * (365 / dias_arr) * 100 if pool["valor_inicial"] > 0 else np.zeros(num_pontos)
                    sim_apr_liq = (prog_pnl_liq / pool["valor_inicial"]) * (365 / dias_arr) * 100 if pool["valor_inicial"] > 0 else np.zeros(num_pontos)
                    sim_apr_tot = sim_apr_fees + sim_apr_liq

                df_metrics = pd.DataFrame({
                    "Data": full_dates.date,
                    "Fees Acumuladas ($)": prog_fees,
                    "PnL / IL da Liquidez ($)": prog_pnl_liq,
                    "APR das Fees (%)": sim_apr_fees,
                    "APR da Liquidez/PnL (%)": sim_apr_liq,
                    "APR Total (%)": sim_apr_tot
                })

                with tab_il_vs_fees:
                    fig_comp = go.Figure()
                    fig_comp.add_trace(go.Scatter(
                        x=df_metrics["Data"], 
                        y=df_metrics["Fees Acumuladas ($)"],
                        mode='lines+markers',
                        name='Fees Acumuladas ($)',
                        line=dict(color='#10b981', width=3)
                    ))
                    fig_comp.add_trace(go.Scatter(
                        x=df_metrics["Data"], 
                        y=df_metrics["PnL / IL da Liquidez ($)"],
                        mode='lines+markers',
                        name='PnL / IL da Liquidez ($)',
                        line=dict(color='#ef4444' if pnl_liquidez_usd < 0 else '#3b82f6', width=2.5)
                    ))
                    fig_comp.update_layout(
                        template="plotly_dark",
                        height=250,
                        margin=dict(l=10, r=10, t=10, b=10),
                        xaxis_title="",
                        yaxis_title="Dólares ($ USD)",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)"
                    )
                    st.plotly_chart(fig_comp, use_container_width=True)

                with tab_apr_perc:
                    metric_sel = st.radio(
                        "Selecione o APR a Visualizar:",
                        options=["APR das Fees (%)", "APR da Liquidez/PnL (%)", "APR Total (%)"],
                        horizontal=True,
                        key=f"metric_choice_{pool['id']}"
                    )

                    if metric_sel == "APR das Fees (%)":
                        color_line = "#8b5cf6"
                    elif metric_sel == "APR da Liquidez/PnL (%)":
                        color_line = "#3b82f6"
                    else:
                        color_line = "#10b981"

                    fig_apr = px.line(df_metrics, x="Data", y=metric_sel, line_shape="spline", markers=True)
                    fig_apr.update_traces(line_color=color_line, line_width=2.5)
                    fig_apr.update_layout(
                        template="plotly_dark",
                        height=230,
                        margin=dict(l=10, r=10, t=10, b=10),
                        xaxis_title="",
                        yaxis_title="",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)"
                    )
                    st.plotly_chart(fig_apr, use_container_width=True)
