import datetime
import json
import sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------
# CONSULTA DE PREÇOS NO DEXSCREENER
# -------------------------------------------------------------
def fetch_dexscreener_price(position_nft_address):
    if not position_nft_address or not isinstance(position_nft_address, str):
        return None, None
    
    clean_addr = position_nft_address.strip()
    if not clean_addr:
        return None, None

    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{clean_addr}"
    try:
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data and "pair" in data and data["pair"]:
                price_usd = float(data["pair"].get("priceUsd", 0))
                price_native = float(data["pair"].get("priceNative", 0))
                return price_usd, price_native
    except Exception:
        pass
    return None, None

# -------------------------------------------------------------
# BASE DE DADOS SQLITE (POOLS E APORTES)
# -------------------------------------------------------------
DB_FILE = "pools_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT,
            rede TEXT,
            estado TEXT,
            valor_inicial REAL,
            valor_atual REAL,
            fees REAL,
            range_min REAL,
            range_max REAL,
            data_entrada TEXT,
            wallet_address TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS aportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_id INTEGER,
            valor REAL,
            data_aporte TEXT,
            FOREIGN KEY (pool_id) REFERENCES pools (id) ON DELETE CASCADE
        )
    ''')

    conn.commit()

    c.execute("SELECT COUNT(*) FROM pools")
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees, range_min, range_max, data_entrada, wallet_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("SOL/PUMP", "Raydium - SOLANA", "Ativa", 2203.0, 2800.62, 27.21, 19.469550, 30.933150, "2026-08-20", ""))
        conn.commit()
    conn.close()

def load_pools():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM pools ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()

    pools = []
    for r in rows:
        try:
            dt_ent = datetime.datetime.strptime(r[9], "%Y-%m-%d").date()
        except Exception:
            dt_ent = datetime.date.today()

        pools.append({
            "id": r[0],
            "par": r[1],
            "rede": r[2],
            "estado": r[3],
            "valor_inicial": float(r[4]),
            "valor_atual": float(r[5]),
            "fees": float(r[6]),
            "range_min": float(r[7]),
            "range_max": float(r[8]),
            "data_entrada": dt_ent,
            "wallet_address": r[10] if len(r) > 10 and r[10] is not None else ""
        })
    return pools

def add_pool_db(par, rede, valor_inicial, valor_atual, fees, r_min, r_max, data_in, wallet_addr):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees, range_min, range_max, data_entrada, wallet_address)
        VALUES (?, ?, 'Ativa', ?, ?, ?, ?, ?, ?, ?)
    ''', (par, rede, valor_inicial, valor_atual, fees, r_min, r_max, data_in.strftime("%Y-%m-%d"), wallet_addr))
    conn.commit()
    conn.close()

def update_pool_db(pool_id, valor_atual, fees, data_entrada, wallet_addr="", r_min=None, r_max=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if r_min is not None and r_max is not None:
        c.execute('''
            UPDATE pools 
            SET valor_atual = ?, fees = ?, data_entrada = ?, wallet_address = ?, range_min = ?, range_max = ?
            WHERE id = ?
        ''', (valor_atual, fees, data_entrada.strftime("%Y-%m-%d"), wallet_addr, r_min, r_max, pool_id))
    else:
        c.execute('''
            UPDATE pools 
            SET valor_atual = ?, fees = ?, data_entrada = ?, wallet_address = ?
            WHERE id = ?
        ''', (valor_atual, fees, data_entrada.strftime("%Y-%m-%d"), wallet_addr, pool_id))
    conn.commit()
    conn.close()

def registrar_aporte_db(pool_id, valor_aporte, data_aporte):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO aportes (pool_id, valor, data_aporte)
        VALUES (?, ?, ?)
    ''', (pool_id, valor_aporte, data_aporte.strftime("%Y-%m-%d")))
    c.execute('''
        UPDATE pools 
        SET valor_atual = valor_atual + ?, valor_inicial = valor_inicial + ?
        WHERE id = ?
    ''', (valor_aporte, valor_aporte, pool_id))
    conn.commit()
    conn.close()

def get_historico_aportes(pool_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT data_aporte, valor FROM aportes 
        WHERE pool_id = ? 
        ORDER BY data_aporte DESC, id DESC
    ''', (pool_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_pool_status_db(pool_id, novo_estado):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE pools SET estado = ? WHERE id = ?", (novo_estado, pool_id))
    conn.commit()
    conn.close()

def delete_pool_db(pool_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pools WHERE id = ?", (pool_id,))
    c.execute("DELETE FROM aportes WHERE pool_id = ?", (pool_id,))
    conn.commit()
    conn.close()

def clear_all_pools_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pools")
    c.execute("DELETE FROM aportes")
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# ESTILOS CSS
# -------------------------------------------------------------
st.markdown("""
    <style>
    .stApp {
        background-color: #0b0e14;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .info-box {
        background-color: #11161d;
        border: 1px solid #1f242c;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 13px;
        color: #9ca3af;
    }
    .info-box strong { color: #f3f4f6; }
    .badge-ativa {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
    }
    .badge-fechada {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
    }
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
    }
    div[data-baseweb="slider"] {
        padding-top: 10px !important;
        padding-bottom: 10px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
        line-height: 1.2 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.80rem !important;
        margin-bottom: -4px !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.80rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# HEADER
col_title, col_actions = st.columns([3, 1])
with col_title:
    st.title("⚡ Gestor de Piscinas de Liquidez")
    st.caption("Acompanhamento de performance e sincronização on-chain DeFi")

pools_data = load_pools()

if "ocultar_detalhes" not in st.session_state:
    st.session_state.ocultar_detalhes = False

DEX_OPTIONS = ["Raydium", "Uniswap v3", "Orca", "Kamino", "PancakeSwap", "Curve", "Meteora", "Cetus", "Outro"]

# MODAL DE SINCRONIZAÇÃO ON-CHAIN COM ATUALIZAÇÃO DIRETA
@st.dialog("🔄 Sincronização On-Chain")
def modal_sincronizar_carteira(pool_id, price_usd=None, price_native=None):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        if price_usd and price_native:
            st.info(f"💡 Cotação do Par no DexScreener: **${price_usd:.6f} USD** ({price_native:.6f} SOL)")

        val_default = float(pool["valor_atual"]) if pool["valor_atual"] > 0 else float(pool["valor_inicial"])

        with st.form(key=f"form_sync_{pool_id}"):
            novo_end = st.text_input("Endereço do Par (DexScreener) ou Position Mint Address:", value=pool.get("wallet_address", ""))
            v_manual = st.number_input("Valor Atual da Pool ($ USD):", min_value=0.0, value=val_default, step=10.0)
            f_manual = st.number_input("Fees Acumuladas ($ USD):", min_value=0.0, value=float(pool["fees"]), step=0.5)

            col_r1, col_r2 = st.columns(2)
            r_min_modal = col_r1.number_input("Range Mín", value=float(pool["range_min"]), format="%.6f", step=0.000001)
            r_max_modal = col_r2.number_input("Range Máx", value=float(pool["range_max"]), format="%.6f", step=0.000001)

            sub = st.form_submit_button("Guardar e Atualizar Pool", type="primary", use_container_width=True)
            if sub:
                valor_final = v_manual if v_manual > 0 else (pool["valor_atual"] if pool["valor_atual"] > 0 else pool["valor_inicial"])
                data_ent = pool.get("data_entrada", datetime.date.today())
                if isinstance(data_ent, str):
                    data_ent = datetime.datetime.strptime(data_ent, "%Y-%m-%d").date()

                update_pool_db(pool_id, valor_final, f_manual, data_ent, novo_end, r_min=r_min_modal, r_max=r_max_modal)
                st.success("Dados atualizados com sucesso!")
                st.rerun()

# MODAL PARA ADICIONAR APORTE
@st.dialog("➕ Registar Novo Aporte")
def modal_adicionar_aporte(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        st.write(f"Registar um novo aporte de liquidez para a pool **{pool['par']}**.")
        with st.form(key=f"form_aporte_{pool_id}"):
            v_aporte = st.number_input("Valor do Aporte ($ USD):", min_value=0.01, value=100.0, step=10.0)
            dt_aporte = st.date_input("Data do Aporte:", datetime.date.today())
            sub = st.form_submit_button("Confirmar e Incrementar Liquidez", type="primary", use_container_width=True)
            if sub:
                registrar_aporte_db(pool_id, v_aporte, dt_aporte)
                st.success(f"Aporte de ${v_aporte:,.2f} adicionado à liquidez da pool!")
                st.rerun()

# MODAL PARA VISUALIZAR HISTÓRICO DE APORTES
@st.dialog("📋 Histórico de Aportes")
def modal_historico_aportes(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        st.write(f"Histórico de aportes da pool **{pool['par']}**:")
        historico = get_historico_aportes(pool_id)
        if not historico:
            st.info("Ainda não existem aportes registados nesta pool.")
        else:
            df_aportes = pd.DataFrame(historico, columns=["Data Aporte", "Valor ($)"])
            df_aportes["Valor ($)"] = df_aportes["Valor ($)"].map(lambda x: f"${x:,.2f}")
            st.dataframe(df_aportes, use_container_width=True, hide_index=True)

# MODAL PARA EDITAR POOL
@st.dialog("⚙️ Editar Parâmetros da Pool")
def modal_atualizar_pool(pool_id):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        st.subheader(f"Pool: {pool['par']}")
        data_ori = pool.get("data_entrada", datetime.date.today())
        if isinstance(data_ori, str):
            data_ori = datetime.datetime.strptime(data_ori, "%Y-%m-%d").date()

        val_default = float(pool["valor_atual"]) if pool["valor_atual"] > 0 else float(pool["valor_inicial"])

        with st.form(key=f"form_edit_modal_{pool_id}"):
            novo_valor_atual = st.number_input("Valor Atual ($ USD)", min_value=0.0, value=val_default, step=10.0)
            novas_fees = st.number_input("Total Fees ($ USD)", min_value=0.0, value=float(pool["fees"]), step=0.5)
            end_carteira = st.text_input("Endereço do Par (DexScreener) / Position Mint Address", value=pool.get("wallet_address", ""))

            col_r1, col_r2 = st.columns(2)
            novo_r_min = col_r1.number_input("Range Mínimo", value=float(pool["range_min"]), format="%.6f", step=0.000001)
            novo_r_max = col_r2.number_input("Range Máximo", value=float(pool["range_max"]), format="%.6f", step=0.000001)

            nova_data_entrada = st.date_input("Data de Entrada", value=data_ori)

            submitted = st.form_submit_button("Guardar Alterações", type="primary", use_container_width=True)
            if submitted:
                valor_final = novo_valor_atual if novo_valor_atual > 0 else (pool["valor_atual"] if pool["valor_atual"] > 0 else pool["valor_inicial"])
                update_pool_db(pool_id, valor_final, novas_fees, nova_data_entrada, end_carteira, r_min=novo_r_min, r_max=novo_r_max)
                st.success(f"Pool {pool['par']} atualizada!")
                st.rerun()

# PAINEL LATERAL
with st.sidebar:
    st.header("➕ Nova Pool")
    with st.form("nova_pool_form", clear_on_submit=True):
        par = st.text_input("Par (ex: SOL/PUMP)", key="form_par")
        rede = st.text_input("Rede / Plataforma", key="form_rede")
        dex = st.selectbox("DEX", DEX_OPTIONS, key="form_dex")
        v_init = st.number_input("Valor Inicial ($)", min_value=0.0, key="form_v_init")
        v_atual = st.number_input("Valor Atual ($)", min_value=0.0, key="form_v_atual")
        fees_in = st.number_input("Fees Pendentes ($)", min_value=0.0, key="form_fees")
        wallet_addr = st.text_input("Endereço do Par / Position Mint Address", key="form_wallet_addr")
        col_r1, col_r2 = st.columns(2)
        r_min = col_r1.number_input("Range Mín", key="form_r_min", format="%.6f", step=0.000001)
        r_max = col_r2.number_input("Range Máx", key="form_r_max", format="%.6f", step=0.000001)
        data_in = st.date_input("Data Entrada", datetime.date.today(), key="form_data_in")

        submit = st.form_submit_button("Adicionar Pool", type="primary")
        if submit:
            nome_par = par if par else "POOL/USD"
            nome_rede = f"{dex} - {rede if rede else 'Rede'}"
            v_actual_calc = v_atual if v_atual > 0 else v_init
            add_pool_db(nome_par, nome_rede, float(v_init), float(v_actual_calc), float(fees_in), float(r_min), float(r_max), data_in, wallet_addr)
            st.success("Pool adicionada!")
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Limpar Portfólio"):
        clear_all_pools_db()
        st.rerun()

# CÁLCULOS DO RESUMO GERAL
total_liquidez = sum(p["valor_atual"] for p in pools_data)
total_fees = sum(p["fees"] for p in pools_data)

aprs_com_peso = []
pesos_iniciais = []

dt_hoje = datetime.date.today()
for p in pools_data:
    dt_ent = p.get("data_entrada", dt_hoje)
    if isinstance(dt_ent, str):
        dt_ent = datetime.datetime.strptime(dt_ent, "%Y-%m-%d").date()

    dias = (dt_hoje - dt_ent).days
    if dias <= 0:
        dias = 1

    total_fees_pool = p.get("fees", 0.0)
    v_init = p.get("valor_inicial", 0.0)

    if v_init > 0:
        apr_p = (total_fees_pool / v_init) * (365 / dias) * 100
        aprs_com_peso.append(apr_p * v_init)
        pesos_iniciais.append(v_init)

total_valor_inicial = sum(pesos_iniciais)
media_apr_fees = sum(aprs_com_peso) / total_valor_inicial if total_valor_inicial > 0 else 0.0

# RESUMO GERAL CARTÕES
st.markdown("### 📌 Resumo Executivo")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
with c2:
    st.metric("Total Fees Acumuladas", f"${total_fees:,.2f}")
with c3:
    st.metric("APR Médio das Fees", f"{media_apr_fees:.2f}%")
with c4:
    label_btn = "👁️ Expandir Detalhes" if st.session_state.ocultar_detalhes else "🙈 Vista Compacta"
    if st.button(label_btn, use_container_width=True):
        st.session_state.ocultar_detalhes = not st.session_state.ocultar_detalhes
        st.rerun()

st.markdown("---")

if not pools_data:
    st.info("Nenhuma piscina registada.")
else:
    if st.session_state.ocultar_detalhes:
        resumo_list = []
        for idx, p in enumerate(pools_data, start=1):
            resumo_list.append({
                "#": idx,
                "Par": p["par"],
                "Plataforma": p["rede"],
                "Estado": p["estado"],
                "Valor Inicial": f"${p['valor_inicial']:,.2f}",
                "Valor Atual": f"${p['valor_atual']:,.2f}",
                "Fees": f"${p['fees']:,.2f}",
                "Range Mín": f"{p['range_min']:.6f}",
                "Range Máx": f"{p['range_max']:.6f}",
                "NFT Position": p.get("wallet_address", "-")
            })
        df_resumo = pd.DataFrame(resumo_list)
        st.dataframe(df_resumo, use_container_width=True, hide_index=True)

    else:
        for idx, pool in enumerate(pools_data, start=1):
            dt_entrada = pool.get("data_entrada", datetime.date.today())
            if isinstance(dt_entrada, str):
                dt_entrada = datetime.datetime.strptime(dt_entrada, "%Y-%m-%d").date()

            dt_hoje = datetime.date.today()
            if dt_entrada >= dt_hoje:
                dt_entrada = dt_hoje - datetime.timedelta(days=1)

            dias_totais = (dt_hoje - dt_entrada).days
            if dias_totais <= 0:
                dias_totais = 1

            total_fees_geradas_pool = pool["fees"]
            pnl = (pool["valor_atual"] + pool["fees"]) - pool["valor_inicial"]
            variacao_pct = ((pool["valor_atual"] - pool["valor_inicial"]) / pool["valor_inicial"]) * 100 if pool["valor_inicial"] > 0 else 0
            apr_total = (total_fees_geradas_pool / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0

            with st.container():
                head_col1, head_col2 = st.columns([2, 3])

                with head_col1:
                    badge_class = "badge-ativa" if pool["estado"] == "Ativa" else "badge-fechada"
                    st.markdown(f"### 🪙 **Pool #{idx}: {pool['par']}** <span class='{badge_class}'>{pool['estado']}</span>", unsafe_allow_html=True)
                    st.caption(f"DEX / Rede: {pool['rede']}")

                with head_col2:
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Valor Atual", f"${pool['valor_atual']:,.2f}")
                    m2.metric("Variação", f"{variacao_pct:+.2f}%", delta_color="normal" if variacao_pct >= 0 else "inverse")
                    m3.metric("PnL Total", f"${pnl:+.2f}", delta_color="normal" if pnl >= 0 else "inverse")
                    m4.metric("APR Total", f"{apr_total:.2f}%")
                    m5.metric("Fees", f"${pool['fees']:,.2f}")

                col_i1, col_i2, col_i3, col_i4 = st.columns(4)
                col_i1.markdown(f"<div class='info-box'>💵 <strong>Valor Inicial:</strong> ${pool['valor_inicial']:,.2f}</div>", unsafe_allow_html=True)
                col_i2.markdown(f"<div class='info-box'>⏱️ <strong>Tempo Ativo:</strong> {dias_totais} dias</div>", unsafe_allow_html=True)
                col_i3.markdown(f"<div class='info-box'>🪙 <strong>Fees Totais:</strong> ${pool['fees']:,.2f}</div>", unsafe_allow_html=True)
                col_i4.markdown(f"<div class='info-box'>🎯 <strong>Range de Preço:</strong> {pool['range_min']:.6f} - {pool['range_max']:.6f}</div>", unsafe_allow_html=True)

                st.write(" ")

                col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)

                if col_b1.button("✏️ Editar", key=f"edit_{pool['id']}", use_container_width=True):
                    modal_atualizar_pool(pool["id"])

                if col_b2.button("🔗 Sincronizar", key=f"sync_{pool['id']}", use_container_width=True):
                    addr = pool.get("wallet_address", "")
                    with st.spinner("A consultar DexScreener..."):
                        p_usd, p_nat = fetch_dexscreener_price(addr)
                        modal_sincronizar_carteira(pool["id"], price_usd=p_usd, price_native=p_nat)

                if col_b3.button("➕ Aporte", key=f"aporte_{pool['id']}", use_container_width=True):
                    modal_adicionar_aporte(pool["id"])

                if col_b4.button("📋 Histórico Aportes", key=f"hist_{pool['id']}", use_container_width=True):
                    modal_historico_aportes(pool["id"])

                with col_b5:
                    with st.popover("⚙️ Mais Opções", use_container_width=True):
                        if st.button("🔒 Fechar/Ativar Pool", key=f"close_{pool['id']}", use_container_width=True):
                            novo_st = "Fechada" if pool["estado"] == "Ativa" else "Ativa"
                            update_pool_status_db(pool["id"], novo_st)
                            st.rerun()

                        if st.button("🗑️ Excluir Pool", key=f"del_{pool['id']}", use_container_width=True, type="primary"):
                            delete_pool_db(pool["id"])
                            st.rerun()

                st.write(" ")
                col_g_title, col_g_btn = st.columns([2, 3])
                with col_g_title:
                    st.markdown("##### 📈 Histórico de Performance")

                with col_g_btn:
                    metric_choice = st.radio("Métrica", options=["Liquidez ($)", "APR das Fees (%)"], horizontal=True, key=f"metric_choice_{pool['id']}", label_visibility="collapsed")

                slider_key = f"slider_range_{pool['id']}"
                if slider_key not in st.session_state:
                    st.session_state[slider_key] = (dt_entrada, dt_hoje)

                dt_inicio_sel, dt_fim_sel = st.session_state[slider_key]
                full_dates = pd.date_range(start=dt_entrada, end=dt_hoje, freq="D")
                num_pontos = len(full_dates)

                if num_pontos == 1:
                    simulated_liquidez = [pool["valor_atual"]]
                    simulated_apr = [apr_total]
                else:
                    np.random.seed(pool["id"])
                    ruido_liq = np.cumsum(np.random.normal(0, 2, size=num_pontos))
                    ruido_liq = ruido_liq - ruido_liq[0]
                    tendencia_liq = np.linspace(pool["valor_inicial"], pool["valor_atual"], num_pontos)
                    simulated_liquidez = tendencia_liq + ruido_liq
                    simulated_liquidez[-1] = pool["valor_atual"]

                    dias_array = np.arange(1, num_pontos + 1)
                    fees_progresso = np.linspace(0.1, total_fees_geradas_pool, num_pontos)
                    simulated_apr = (fees_progresso / pool["valor_inicial"]) * (365 / dias_array) * 100 if pool["valor_inicial"] > 0 else np.zeros(num_pontos)
                    simulated_apr[-1] = apr_total

                df_full = pd.DataFrame({
                    "Data": full_dates.date,
                    "Liquidez ($)": simulated_liquidez,
                    "APR das Fees (%)": simulated_apr
                })

                df_chart = df_full[(df_full["Data"] >= dt_inicio_sel) & (df_full["Data"] <= dt_fim_sel)]

                if metric_choice == "Liquidez ($)":
                    y_col = "Liquidez ($)"
                    line_color = "#10b981"
                else:
                    y_col = "APR das Fees (%)"
                    line_color = "#8b5cf6"

                fig = px.line(df_chart, x="Data", y=y_col, line_shape="spline", markers=True)
                fig.update_traces(line_color=line_color, line_width=2.5)
                fig.update_layout(
                    template="plotly_dark",
                    height=250,
                    margin=dict(l=10, r=10, t=10, b=10),
                    xaxis_title="",
                    yaxis_title="",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig, use_container_width=True)

                selected_range = st.slider("Seleção de Intervalo", min_value=dt_entrada, max_value=dt_hoje, value=st.session_state[slider_key], format="YYYY-MM-DD", key=slider_key, label_visibility="collapsed")

                st.markdown("---")
