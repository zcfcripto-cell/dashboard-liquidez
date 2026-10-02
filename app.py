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
# BASE DE DADOS SQLITE LOCAL PERSISTENTE
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
            fees REAL DEFAULT 0,
            range_min REAL DEFAULT 0,
            range_max REAL DEFAULT 0,
            data_entrada TEXT,
            wallet_address TEXT DEFAULT ''
        )
    ''')

    c.execute("PRAGMA table_info(pools)")
    existing_cols = [col[1] for col in c.fetchall()]

    if "fees" not in existing_cols:
        c.execute("ALTER TABLE pools ADD COLUMN fees REAL DEFAULT 0")
    if "range_min" not in existing_cols:
        c.execute("ALTER TABLE pools ADD COLUMN range_min REAL DEFAULT 0")
    if "range_max" not in existing_cols:
        c.execute("ALTER TABLE pools ADD COLUMN range_max REAL DEFAULT 0")
    if "wallet_address" not in existing_cols:
        c.execute("ALTER TABLE pools ADD COLUMN wallet_address TEXT DEFAULT ''")

    c.execute('''
        CREATE TABLE IF NOT EXISTS aportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_id INTEGER,
            valor REAL,
            data_aporte TEXT,
            FOREIGN KEY (pool_id) REFERENCES pools (id) ON DELETE CASCADE
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS saques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_id INTEGER,
            valor REAL,
            data_saque TEXT,
            FOREIGN KEY (pool_id) REFERENCES pools (id) ON DELETE CASCADE
        )
    ''')

    conn.commit()

    c.execute("SELECT COUNT(*) FROM pools")
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees, range_min, range_max, data_entrada, wallet_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("SOL/PUMP", "Raydium - SOLANA", "Ativa", 2203.0, 2800.62, 175.50, 19.469550, 30.933150, "2026-08-20", ""))
        conn.commit()
    conn.close()

def load_pools():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, par, rede, estado, valor_inicial, valor_atual, fees, range_min, range_max, data_entrada, wallet_address FROM pools ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()

    pools = []
    for r in rows:
        try:
            dt_ent = datetime.datetime.strptime(str(r[9]), "%Y-%m-%d").date()
        except Exception:
            dt_ent = datetime.date.today()

        pools.append({
            "id": int(r[0]),
            "par": str(r[1] or "POOL/USD"),
            "rede": str(r[2] or "DEX"),
            "estado": str(r[3] or "Ativa"),
            "valor_inicial": float(r[4] or 0),
            "valor_atual": float(r[5] or 0),
            "fees": float(r[6] or 0),
            "range_min": float(r[7] or 0),
            "range_max": float(r[8] or 0),
            "data_entrada": dt_ent,
            "wallet_address": str(r[10] or "")
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
        ''', (valor_atual, fees, data_entrada.strftime("%Y-%m-%d"), wallet_addr, r_min, r_max, int(pool_id)))
    else:
        c.execute('''
            UPDATE pools 
            SET valor_atual = ?, fees = ?, data_entrada = ?, wallet_address = ?
            WHERE id = ?
        ''', (valor_atual, fees, data_entrada.strftime("%Y-%m-%d"), wallet_addr, int(pool_id)))
    conn.commit()
    conn.close()

def registrar_aporte_db(pool_id, valor_aporte, data_aporte):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO aportes (pool_id, valor, data_aporte)
        VALUES (?, ?, ?)
    ''', (int(pool_id), valor_aporte, data_aporte.strftime("%Y-%m-%d")))
    c.execute('''
        UPDATE pools 
        SET valor_atual = valor_atual + ?, valor_inicial = valor_inicial + ?
        WHERE id = ?
    ''', (valor_aporte, valor_aporte, int(pool_id)))
    conn.commit()
    conn.close()

def get_historico_aportes(pool_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, data_aporte, valor FROM aportes WHERE pool_id = ? ORDER BY id DESC', (int(pool_id),))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_aporte_db(aporte_id, pool_id, valor_aporte):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM aportes WHERE id = ?", (int(aporte_id),))
    c.execute('''
        UPDATE pools 
        SET valor_atual = MAX(0, valor_atual - ?), valor_inicial = MAX(0, valor_inicial - ?)
        WHERE id = ?
    ''', (valor_aporte, valor_aporte, int(pool_id)))
    conn.commit()
    conn.close()

def registrar_saque_db(pool_id, valor_saque, data_saque):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO saques (pool_id, valor, data_saque)
        VALUES (?, ?, ?)
    ''', (int(pool_id), valor_saque, data_saque.strftime("%Y-%m-%d")))
    c.execute('''
        UPDATE pools 
        SET fees = fees + ?
        WHERE id = ?
    ''', (valor_saque, int(pool_id)))
    conn.commit()
    conn.close()

def get_historico_saques(pool_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, data_saque, valor FROM saques WHERE pool_id = ? ORDER BY id DESC', (int(pool_id),))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_saque_db(saque_id, pool_id, valor_saque):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM saques WHERE id = ?", (int(saque_id),))
    c.execute('''
        UPDATE pools 
        SET fees = MAX(0, fees - ?)
        WHERE id = ?
    ''', (valor_saque, int(pool_id)))
    conn.commit()
    conn.close()

def update_pool_status_db(pool_id, novo_estado):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE pools SET estado = ? WHERE id = ?", (novo_estado, int(pool_id)))
    conn.commit()
    conn.close()

def delete_pool_db(pool_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pools WHERE id = ?", (int(pool_id),))
    c.execute("DELETE FROM aportes WHERE pool_id = ?", (int(pool_id),))
    c.execute("DELETE FROM saques WHERE pool_id = ?", (int(pool_id),))
    conn.commit()
    conn.close()

def clear_all_pools_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pools")
    c.execute("DELETE FROM aportes")
    c.execute("DELETE FROM saques")
    conn.commit()
    conn.close()

# CONSULTA DE PREÇOS DEXSCREENER
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

init_db()

# ESTILOS CSS ADAPTATIVOS PARA ECRÃS PEQUENOS E GRANDES
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
    
    /* REGRAS ANTI-CORTE DE TEXTO NAS MÉTRICAS */
    [data-testid="stMetricValue"] {
        font-size: calc(1.0rem + 0.35vw) !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        white-space: nowrap !important;
        margin-bottom: -2px !important;
    }
    </style>
""", unsafe_allow_html=True)

# HEADER
st.title("⚡ Gestor de Piscinas de Liquidez")
st.caption("Acompanhamento de performance e gestão DeFi")

pools_data = load_pools()

DEX_OPTIONS = ["Raydium", "Uniswap v3", "Orca", "Kamino", "PancakeSwap", "Curve", "Meteora", "Cetus", "Outro"]

# MODAL RESUMO HISTÓRICO GERAL (1 LINHA POR POOL)
@st.dialog("📋 Resumo Histórico das Piscinas")
def modal_tabela_resumo_historico():
    st.subheader("📋 Resumo Geral de Todas as Pools")
    st.caption("Estatísticas consolidadas de todas as posições (Ativas e Encerradas).")
    
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
            "Valor Inicial": f"${v_init:,.2f}",
            "Valor Atual": f"${v_atual:,.2f}",
            "Fees Acumuladas": f"${fees:,.2f}",
            "PnL Total": f"${pnl:+,.2f}",
            "APR Total (%)": f"{apr:.2f}%",
            "Data Entrada": dt_ent.strftime("%Y-%m-%d")
        })

    df_geral = pd.DataFrame(resumo_rows)
    st.dataframe(df_geral, use_container_width=True, hide_index=True)

# MODAIS DE OPERAÇÃO
@st.dialog("🔄 Sincronização On-Chain")
def modal_sincronizar_carteira(pool_id, price_usd=None, price_native=None):
    pool = next((p for p in pools_data if p["id"] == pool_id), None)
    if pool is not None:
        if price_usd and price_native:
            st.info(f"💡 Cotação do Par no DexScreener: **${price_usd:.6f} USD** ({price_native:.6f} SOL)")
        val_default = float(pool["valor_atual"]) if pool["valor_atual"] > 0 else float(pool["valor_inicial"])

        with st.form(key=f"form_sync_{pool_id}"):
            novo_end = st.text_input("Endereço do Par / Position Mint Address:", value=pool.get("wallet_address", ""))
            v_manual = st.number_input("Valor Atual da Pool ($ USD):", min_value=0.0, value=val_default, step=10.0)
            f_manual = st.number_input("Fees Acumuladas Totais ($ USD):", min_value=0.0, value=float(pool["fees"]), step=0.5)
            col_r1, col_r2 = st.columns(2)
            r_min_modal = col_r1.number_input("Range Mín", value=float(pool["range_min"]), format="%.6f", step=0.000001)
            r_max_modal = col_r2.number_input("Range Máx", value=float(pool["range_max"]), format="%.6f", step=0.000001)

            sub = st.form_submit_button("Guardar e Atualizar Pool", type="primary", use_container_width=True)
            if sub:
                valor_final = v_manual if v_manual > 0 else pool["valor_inicial"]
                data_ent = pool.get("data_entrada", datetime.date.today())
                update_pool_db(pool_id, valor_final, f_manual, data_ent, novo_end, r_min=r_min_modal, r_max=r_max_modal)
                st.success("Dados atualizados!")
                st.rerun()

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
                    st.success("Aporte guardado!")
                    st.rerun()
        with tab_hist:
            historico = get_historico_aportes(pool_id)
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
            novo_v_atual = st.number_input("Valor Atual ($ USD)", min_value=0.0, value=float(pool["valor_atual"]), step=10.0)
            novas_fees = st.number_input("Total Fees ($ USD)", min_value=0.0, value=float(pool["fees"]), step=0.5)
            end_c = st.text_input("Position Address", value=pool.get("wallet_address", ""))
            col_r1, col_r2 = st.columns(2)
            novo_r_min = col_r1.number_input("Range Mín", value=float(pool["range_min"]), format="%.6f", step=0.000001)
            novo_r_max = col_r2.number_input("Range Máx", value=float(pool["range_max"]), format="%.6f", step=0.000001)
            nova_dt = st.date_input("Data Entrada", value=pool["data_entrada"])
            if st.form_submit_button("Guardar Alterações", type="primary", use_container_width=True):
                update_pool_db(pool_id, novo_v_atual, novas_fees, nova_dt, end_c, r_min=novo_r_min, r_max=novo_r_max)
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
        wallet_addr = st.text_input("Position Address")
        col_r1, col_r2 = st.columns(2)
        r_min = col_r1.number_input("Range Mín", format="%.6f", step=0.000001)
        r_max = col_r2.number_input("Range Máx", format="%.6f", step=0.000001)
        data_in = st.date_input("Data Entrada", datetime.date.today())

        if st.form_submit_button("Adicionar Pool", type="primary"):
            nome_par = par if par else "POOL/USD"
            nome_rede = f"{dex} - {rede if rede else 'Rede'}"
            v_actual_calc = v_atual if v_atual > 0 else v_init
            add_pool_db(nome_par, nome_rede, float(v_init), float(v_actual_calc), float(fees_in), float(r_min), float(r_max), data_in, wallet_addr)
            st.success("Pool gravada!")
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Limpar Portfólio"):
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

        total_fees_geradas = pool["fees"]
        pnl_valor = (pool["valor_atual"] + total_fees_geradas) - pool["valor_inicial"]
        variacao_pct = ((pool["valor_atual"] - pool["valor_inicial"]) / pool["valor_inicial"]) * 100 if pool["valor_inicial"] > 0 else 0
        
        # APRs
        apr_fees = (total_fees_geradas / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0
        apr_liquidez = ((pool["valor_atual"] - pool["valor_inicial"]) / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0
        apr_total = (pnl_valor / pool["valor_inicial"]) * (365 / dias_totais) * 100 if pool["valor_inicial"] > 0 else 0

        with st.container():
            # PROPORÇÕES AJUSTADAS (40% PARA O TÍTULO, 60% DISTRIBUÍDO PARA MÉTRICAS SEM CORTES)
            head_col1, head_col2 = st.columns([1.5, 3.5])
            with head_col1:
                badge_class = "badge-ativa" if pool["estado"] == "Ativa" else "badge-fechada"
                st.markdown(f"### 🪙 **Pool #{idx}: {pool['par']}** <span class='{badge_class}'>{pool['estado']}</span>", unsafe_allow_html=True)
                st.caption(f"DEX / Rede: {pool['rede']}")

            with head_col2:
                m1, m2, m3, m4, m5 = st.columns([1, 1, 1, 1, 1])
                m1.metric("Valor Atual", f"${pool['valor_atual']:,.2f}")
                m2.metric("Variação", f"{variacao_pct:+.2f}%")
                m3.metric("PnL Total", f"${pnl_valor:+.2f}")
                m4.metric("APR Total", f"{apr_total:.2f}%")
                m5.metric("Fees", f"${pool['fees']:,.2f}")

            col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
            if col_b1.button("✏️ Editar", key=f"edit_{pool['id']}", use_container_width=True):
                modal_atualizar_pool(pool["id"])

            if col_b2.button("🔗 Sincronizar", key=f"sync_{pool['id']}", use_container_width=True):
                p_usd, p_nat = fetch_dexscreener_price(pool.get("wallet_address", ""))
                modal_sincronizar_carteira(pool["id"], price_usd=p_usd, price_native=p_nat)

            if col_b3.button("➕ Aporte", key=f"aporte_{pool['id']}", use_container_width=True):
                modal_gerir_aportes(pool["id"])

            if col_b4.button("💸 Sacar Fees", key=f"sacar_{pool['id']}", use_container_width=True):
                modal_gerir_saques(pool["id"])

            with col_b5:
                with st.popover("⚙️ Mais Opções", use_container_width=True):
                    if st.button("🔒 Fechar/Ativar", key=f"close_{pool['id']}", use_container_width=True):
                        update_pool_status_db(pool["id"], "Fechada" if pool["estado"] == "Ativa" else "Ativa")
                        st.rerun()
                    if st.button("🗑️ Excluir Pool", key=f"del_{pool['id']}", use_container_width=True, type="primary"):
                        delete_pool_db(pool["id"])
                        st.rerun()

            # GRÁFICO DE APR DEBAIXO DE CADA POOL COM CONTROLO
            show_chart_key = f"show_chart_{pool['id']}"
            if show_chart_key not in st.session_state:
                st.session_state[show_chart_key] = True

            chart_btn_col1, chart_btn_col2 = st.columns([3, 1])
            with chart_btn_col2:
                btn_label = "🙈 Esconder Gráfico" if st.session_state[show_chart_key] else "📈 Mostrar Gráfico APR"
                if st.button(btn_label, key=f"toggle_chart_{pool['id']}", use_container_width=True):
                    st.session_state[show_chart_key] = not st.session_state[show_chart_key]
                    st.rerun()

            if st.session_state[show_chart_key]:
                with chart_btn_col1:
                    metric_sel = st.radio(
                        "Selecione o APR a Visualizar:",
                        options=["APR das Fees (%)", "APR da Liquidez/PnL (%)", "APR Total (%)"],
                        horizontal=True,
                        key=f"metric_choice_{pool['id']}"
                    )

                full_dates = pd.date_range(start=dt_entrada, end=dt_hoje, freq="D")
                num_pontos = len(full_dates)

                if num_pontos == 1:
                    sim_apr_fees = [apr_fees]
                    sim_apr_liq = [apr_liquidez]
                    sim_apr_tot = [apr_total]
                else:
                    dias_arr = np.arange(1, num_pontos + 1)
                    prog_fees = np.linspace(0.1, total_fees_geradas, num_pontos)
                    sim_apr_fees = (prog_fees / pool["valor_inicial"]) * (365 / dias_arr) * 100 if pool["valor_inicial"] > 0 else np.zeros(num_pontos)

                    np.random.seed(pool["id"])
                    ruido = np.cumsum(np.random.normal(0, 1.5, size=num_pontos))
                    tendencia_val = np.linspace(pool["valor_inicial"], pool["valor_atual"], num_pontos)
                    prog_liq = tendencia_val + (ruido - ruido[0])
                    prog_liq[-1] = pool["valor_atual"]

                    sim_apr_liq = ((prog_liq - pool["valor_inicial"]) / pool["valor_inicial"]) * (365 / dias_arr) * 100 if pool["valor_inicial"] > 0 else np.zeros(num_pontos)
                    sim_apr_tot = sim_apr_fees + sim_apr_liq

                df_apr = pd.DataFrame({
                    "Data": full_dates.date,
                    "APR das Fees (%)": sim_apr_fees,
                    "APR da Liquidez/PnL (%)": sim_apr_liq,
                    "APR Total (%)": sim_apr_tot
                })

                if metric_sel == "APR das Fees (%)":
                    color_line = "#8b5cf6"
                elif metric_sel == "APR da Liquidez/PnL (%)":
                    color_line = "#3b82f6"
                else:
                    color_line = "#10b981"

                fig = px.line(df_apr, x="Data", y=metric_sel, line_shape="spline", markers=True)
                fig.update_traces(line_color=color_line, line_width=2.5)
                fig.update_layout(
                    template="plotly_dark",
                    height=240,
                    margin=dict(l=10, r=10, t=10, b=10),
                    xaxis_title="",
                    yaxis_title="",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
