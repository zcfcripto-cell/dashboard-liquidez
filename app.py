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
# CONSULTA ON-CHAIN
# -------------------------------------------------------------
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"


def fetch_onchain_position_and_price(position_nft_address: str):
  if not position_nft_address:
    return None, False

  clean_addr = position_nft_address.strip()
  price_usd = 0.0
  try:
    url_dex = (
        f"https://api.dexscreener.com/latest/dex/pairs/solana/{clean_addr}"
    )
    res_dex = requests.get(url_dex, timeout=6)
    if res_dex.status_code == 200:
      data_dex = res_dex.json()
      if data_dex and "pair" in data_dex and data_dex["pair"]:
        price_usd = float(data_dex["pair"].get("priceUsd", 0))
  except Exception:
    pass

  payload = {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "getAccountInfo",
      "params": [clean_addr, {"encoding": "jsonParsed"}],
  }

  try:
    res_rpc = requests.post(SOLANA_RPC_URL, json=payload, timeout=8)
    if res_rpc.status_code == 200:
      data_rpc = res_rpc.json()
      if "result" in data_rpc and data_rpc["result"]["value"]:
        return price_usd, True
  except Exception:
    pass

  return price_usd, False


# -------------------------------------------------------------
# BASE DE DADOS SQLITE
# -------------------------------------------------------------
DB_FILE = "pools_data.db"


def init_db():
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute("""
        CREATE TABLE IF NOT EXISTS pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT,
            rede TEXT,
            estado TEXT,
            valor_inicial REAL,
            valor_atual REAL,
            fees_sacadas REAL,
            fees_reinvestidas REAL,
            fees_nao_coletadas REAL,
            range_min REAL,
            range_max REAL,
            data_entrada TEXT,
            wallet_address TEXT
        )
    """)
  conn.commit()

  c.execute("PRAGMA table_info(pools)")
  columns = [col[1] for col in c.fetchall()]
  if "wallet_address" not in columns:
    c.execute("ALTER TABLE pools ADD COLUMN wallet_address TEXT")
    conn.commit()

  c.execute("SELECT COUNT(*) FROM pools")
  if c.fetchone()[0] == 0:
    c.execute(
        """
            INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees_sacadas, fees_reinvestidas, fees_nao_coletadas, range_min, range_max, data_entrada, wallet_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "SOL/PUMP",
            "Raydium - SOLANA",
            "Ativa",
            2203.0,
            2815.0,
            50.0,
            0.0,
            25.00,
            19.469550,
            30.933150,
            "2026-08-20",
            "",
        ),
    )
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
      dt_ent = datetime.datetime.strptime(r[11], "%Y-%m-%d").date()
    except Exception:
      dt_ent = datetime.date.today()

    pools.append({
        "id": r[0],
        "par": r[1],
        "rede": r[2],
        "estado": r[3],
        "valor_inicial": float(r[4]),
        "valor_atual": float(r[5]),
        "fees_sacadas": float(r[6]),
        "fees_reinvestidas": float(r[7]),
        "fees_nao_coletadas": float(r[8]),
        "range_min": float(r[9]),
        "range_max": float(r[10]),
        "data_entrada": dt_ent,
        "wallet_address": r[12] if len(r) > 12 and r[12] else "",
    })
  return pools


def add_pool_db(
    par,
    rede,
    valor_inicial,
    valor_atual,
    fees_sacadas,
    fees_reinvestidas,
    fees_pendentes,
    r_min,
    r_max,
    data_in,
    wallet_addr,
):
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute(
      """
        INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees_sacadas, fees_reinvestidas, fees_nao_coletadas, range_min, range_max, data_entrada, wallet_address)
        VALUES (?, ?, 'Ativa', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          par,
          rede,
          valor_inicial,
          valor_atual,
          fees_sacadas,
          fees_reinvestidas,
          fees_pendentes,
          r_min,
          r_max,
          data_in.strftime("%Y-%m-%d"),
          wallet_addr,
      ),
  )
  conn.commit()
  conn.close()


def update_pool_db(
    pool_id,
    valor_atual,
    fees_pendentes,
    data_entrada,
    wallet_addr="",
    r_min=None,
    r_max=None,
):
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  if r_min is not None and r_max is not None:
    c.execute(
        """
            UPDATE pools 
            SET valor_atual = ?, fees_nao_coletadas = ?, data_entrada = ?, wallet_address = ?, range_min = ?, range_max = ?
            WHERE id = ?
        """,
        (
            valor_atual,
            fees_pendentes,
            data_entrada.strftime("%Y-%m-%d"),
            wallet_addr,
            r_min,
            r_max,
            pool_id,
        ),
    )
  else:
    c.execute(
        """
            UPDATE pools 
            SET valor_atual = ?, fees_nao_coletadas = ?, data_entrada = ?, wallet_address = ?
            WHERE id = ?
        """,
        (
            valor_atual,
            fees_pendentes,
            data_entrada.strftime("%Y-%m-%d"),
            wallet_addr,
            pool_id,
        ),
    )
  conn.commit()
  conn.close()


def update_pool_status_db(pool_id, novo_estado):
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute(
      "UPDATE pools SET estado = ? WHERE id = ?", (novo_estado, pool_id)
  )
  conn.commit()
  conn.close()


def update_pool_fees_db(pool_id, novo_v_atual, f_sac, f_reinv, f_pend):
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute(
      """
        UPDATE pools 
        SET valor_atual = ?, fees_sacadas = ?, fees_reinvestidas = ?, fees_nao_coletadas = ?
        WHERE id = ?
    """,
      (novo_v_atual, f_sac, f_reinv, f_pend, pool_id),
  )
  conn.commit()
  conn.close()


def delete_pool_db(pool_id):
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute("DELETE FROM pools WHERE id = ?", (pool_id,))
  conn.commit()
  conn.close()


def clear_all_pools_db():
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute("DELETE FROM pools")
  conn.commit()
  conn.close()


init_db()

# -------------------------------------------------------------
# ESTILOS CSS PROFISSIONAIS
# -------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Fundo geral e tipografia */
    .stApp {
        background-color: #0b0e14;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Cartões e Contentores */
    .metric-card {
        background: #161b22;
        border: 1px solid #21262d;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    .info-box {
        background-color: #11161d;
        border: 1px solid #1f242c;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 13px;
        color: #9ca3af;
    }

    .info-box strong {
        color: #f3f4f6;
    }

    /* Badges de Estado */
    .badge-ativa {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .badge-fechada {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    /* Estilização de Botões */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease-in-out !important;
    }

    /* Ajuste de Espaçamento dos Sliders */
    div[data-baseweb="slider"] {
        padding-top: 10px !important;
        padding-bottom: 10px !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# HEADER
col_title, col_actions = st.columns([3, 1])
with col_title:
  st.title("⚡ Gestor de Piscinas de Liquidez")
  st.caption("Acompanhamento de performance e sincronização on-chain DeFi")

pools_data = load_pools()

if "ocultar_detalhes" not in st.session_state:
  st.session_state.ocultar_detalhes = False

DEX_OPTIONS = [
    "Raydium",
    "Uniswap v3",
    "Orca",
    "Kamino",
    "PancakeSwap",
    "Curve",
    "Meteora",
    "Cetus",
    "Outro",
]


# Modal para editar pool geral
@st.dialog("⚙️ Editar Parâmetros da Pool")
def modal_atualizar_pool(pool_id):
  pool = next((p for p in pools_data if p["id"] == pool_id), None)

  if pool is not None:
    st.subheader(f"Pool: {pool['par']}")

    data_ori = pool.get("data_entrada", datetime.date.today())
    if isinstance(data_ori, str):
      data_ori = datetime.datetime.strptime(data_ori, "%Y-%m-%d").date()

    val_default = (
        float(pool["valor_atual"])
        if pool["valor_atual"] > 0
        else float(pool["valor_inicial"])
    )

    with st.form(key=f"form_edit_modal_{pool_id}"):
      novo_valor_atual = st.number_input(
          "Valor Atual ($ USD)", min_value=0.0, value=val_default, step=10.0
      )
      novas_fees_pendentes = st.number_input(
          "Fees Pendentes ($ USD)",
          min_value=0.0,
          value=float(pool["fees_nao_coletadas"]),
          step=0.5,
      )
      end_carteira = st.text_input(
          "Position Mint Address (NFT ID)",
          value=pool.get("wallet_address", ""),
      )

      col_r1, col_r2 = st.columns(2)
      novo_r_min = col_r1.number_input(
          "Range Mínimo",
          value=float(pool["range_min"]),
          format="%.6f",
          step=0.000001,
      )
      novo_r_max = col_r2.number_input(
          "Range Máximo",
          value=float(pool["range_max"]),
          format="%.6f",
          step=0.000001,
      )

      nova_data_entrada = st.date_input("Data de Entrada", value=data_ori)

      submitted = st.form_submit_button(
          "Guardar Alterações", type="primary", use_container_width=True
      )

      if submitted:
        valor_final = (
            novo_valor_atual
            if novo_valor_atual > 0
            else (
                pool["valor_atual"]
                if pool["valor_atual"] > 0
                else pool["valor_inicial"]
            )
        )
        update_pool_db(
            pool_id,
            valor_final,
            novas_fees_pendentes,
            nova_data_entrada,
            end_carteira,
            r_min=novo_r_min,
            r_max=novo_r_max,
        )
        st.success(f"Pool {pool['par']} atualizada!")
        st.rerun()


# Painel Lateral
with st.sidebar:
  st.header("➕ Nova Pool")

  with st.form("nova_pool_form", clear_on_submit=True):
    par = st.text_input("Par (ex: SOL/PUMP)", key="form_par")
    rede = st.text_input("Rede / Plataforma", key="form_rede")
    dex = st.selectbox("DEX", DEX_OPTIONS, key="form_dex")
    v_init = st.number_input("Valor Inicial ($)", min_value=0.0, key="form_v_init")
    v_atual = st.number_input(
        "Valor Atual ($)", min_value=0.0, key="form_v_atual"
    )
    f_sacadas = st.number_input(
        "Fees Sacadas ($)", min_value=0.0, key="form_f_sacadas"
    )
    f_reinvestidas = st.number_input(
        "Fees Reinvestidas ($)", min_value=0.0, key="form_f_reinvestidas"
    )
    fees_pendentes = st.number_input(
        "Fees Pendentes ($)", min_value=0.0, key="form_fees_pendentes"
    )
    wallet_addr = st.text_input(
        "Position Mint Address (NFT)", key="form_wallet_addr"
    )
    col_r1, col_r2 = st.columns(2)
    r_min = col_r1.number_input(
        "Range Mín", key="form_r_min", format="%.6f", step=0.000001
    )
    r_max = col_r2.number_input(
        "Range Máx", key="form_r_max", format="%.6f", step=0.000001
    )
    data_in = st.date_input(
        "Data Entrada", datetime.date.today(), key="form_data_in"
    )

    submit = st.form_submit_button("Adicionar Pool", type="primary")
    if submit:
      nome_par = par if par else "POOL/USD"
      nome_rede = f"{dex} - {rede if rede else 'Rede'}"
      v_actual_calc = v_atual if v_atual > 0 else v_init

      add_pool_db(
          nome_par,
          nome_rede,
          float(v_init),
          float(v_actual_calc),
          float(f_sacadas),
          float(f_reinvestidas),
          float(fees_pendentes),
          float(r_min),
          float(r_max),
          data_in,
          wallet_addr,
      )

      st.success("Pool adicionada!")
      st.rerun()

  st.markdown("---")
  if st.button("🗑️ Limpar Portfólio"):
    clear_all_pools_db()
    st.rerun()

# CÁLCULOS DO RESUMO GERAL
total_liquidez = sum(p["valor_atual"] for p in pools_data)
total_fees_geradas = sum(
    p["fees_sacadas"] + p["fees_reinvestidas"] for p in pools_data
)

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

  total_fees_pool = (
      p.get("fees_sacadas", 0.0)
      + p.get("fees_reinvestidas", 0.0)
      + p.get("fees_nao_coletadas", 0.0)
  )
  v_init = p.get("valor_inicial", 0.0)

  if v_init > 0:
    apr_p = (total_fees_pool / v_init) * (365 / dias) * 100
    aprs_com_peso.append(apr_p * v_init)
    pesos_iniciais.append(v_init)

total_valor_inicial = sum(pesos_iniciais)
media_apr_fees = (
    sum(aprs_com_peso) / total_valor_inicial if total_valor_inicial > 0 else 0.0
)

# RESUMO GERAL CARTÕES
st.markdown("### 📌 Resumo Executivo")
c1, c2, c3, c4 = st.columns(4)

with c1:
  st.metric("Total Em Liquidez", f"${total_liquidez:,.2f}")
with c2:
  st.metric("Total Fees Coletadas", f"${total_fees_geradas:,.2f}")
with c3:
  st.metric("APR Médio do Portfólio", f"{media_apr_fees:.2f}%")
with c4:
  label_btn = (
      "👁️ Expandir Detalhes"
      if st.session_state.ocultar_detalhes
      else "🙈 Vista Compacta"
  )
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
      f_sac = p.get("fees_sacadas", 0.0)
      f_reinv = p.get("fees_reinvestidas", 0.0)
      f_pend = p.get("fees_nao_coletadas", 0.0)

      resumo_list.append({
          "#": idx,
          "Par": p["par"],
          "Plataforma": p["rede"],
          "Estado": p["estado"],
          "Valor Inicial": f"${p['valor_inicial']:,.2f}",
          "Valor Atual": f"${p['valor_atual']:,.2f}",
          "Fees Geradas": f"${f_sac + f_reinv:,.2f}",
          "Fees Pendentes": f"${f_pend:,.2f}",
          "Range Mín": f"{p['range_min']:.6f}",
          "Range Máx": f"{p['range_max']:.6f}",
          "NFT Position": p.get("wallet_address", "-"),
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

      total_fees_geradas_pool = (
          pool["fees_sacadas"]
          + pool["fees_reinvestidas"]
          + pool["fees_nao_coletadas"]
      )
      pnl = (pool["valor_atual"] + pool["fees_sacadas"]) - pool["valor_inicial"]
      variacao_pct = (
          (
              (pool["valor_atual"] - pool["valor_inicial"])
              / pool["valor_inicial"]
          )
          * 100
          if pool["valor_inicial"] > 0
          else 0
      )
      apr_total = (
          (total_fees_geradas_pool / pool["valor_inicial"])
          * (365 / dias_totais)
          * 100
          if pool["valor_inicial"] > 0
          else 0
      )

      # CARTÃO DA POOL
      with st.container():
        head_col1, head_col2 = st.columns([2, 3])

        with head_col1:
          badge_class = (
              "badge-ativa" if pool["estado"] == "Ativa" else "badge-fechada"
          )
          st.markdown(
              f"### 🪙 **Pool #{idx}: {pool['par']}** <span"
              f" class='{badge_class}'>{pool['estado']}</span>",
              unsafe_allow_html=True,
          )
          st.caption(f"DEX / Rede: {pool['rede']}")

        with head_col2:
          m1, m2, m3, m4, m5 = st.columns(5)
          m1.metric("Valor Atual", f"${pool['valor_atual']:,.2f}")
          m2.metric(
              "Variação",
              f"{variacao_pct:+.2f}%",
              delta_color="normal" if variacao_pct >= 0 else "inverse",
          )
          m3.metric(
              "PnL Total",
              f"${pnl:+.2f}",
              delta_color="normal" if pnl >= 0 else "inverse",
          )
          m4.metric("APR Total", f"{apr_total:.2f}%")
          m5.metric("Fees Pendentes", f"${pool['fees_nao_coletadas']:,.2f}")

        # BLOCO INFORMATIVO COMPACTO
        col_i1, col_i2, col_i3, col_i4 = st.columns(4)
        col_i1.markdown(
            f"<div class='info-box'>💵 <strong>Valor Inicial:</strong>"
            f" ${pool['valor_inicial']:,.2f}</div>",
            unsafe_allow_html=True,
        )
        col_i2.markdown(
            f"<div class='info-box'>⏱️ <strong>Tempo Ativo:</strong>"
            f" {dias_totais} dias</div>",
            unsafe_allow_html=True,
        )
        col_i3.markdown(
            f"<div class='info-box'>💰 <strong>Fees (Sacadas / Reinv):</strong>"
            f" ${pool['fees_sacadas']:,.2f} /"
            f" ${pool['fees_reinvestidas']:,.2f}</div>",
            unsafe_allow_html=True,
        )
        col_i4.markdown(
            f"<div class='info-box'>🎯 <strong>Range de Preço:</strong>"
            f" {pool['range_min']:.6f} - {pool['range_max']:.6f}</div>",
            unsafe_allow_html=True,
        )

        st.write(" ")

        # AÇÕES DA POOL
        col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)

        if col_b1.button(
            "✏️ Editar", key=f"edit_{pool['id']}", use_container_width=True
        ):
          modal_atualizar_pool(pool["id"])

        if col_b2.button(
            "🔗 Sincronizar", key=f"sync_{pool['id']}", use_container_width=True
        ):
          addr = pool.get("wallet_address", "")
          if not addr:
            st.warning("Adiciona o Position Mint Address na edição.")
          else:
            with st.spinner("A ligar ao RPC..."):
              price_usd, success = fetch_onchain_position_and_price(addr)
              if success:
                st.success("Verificado On-Chain!")
                st.rerun()
              else:
                st.info("Consulta efetuada.")

        if col_b3.button(
            "🔄 Reinvestir",
            key=f"reinvest_{pool['id']}",
            use_container_width=True,
        ):
          if pool["fees_nao_coletadas"] > 0:
            fees_temp = pool["fees_nao_coletadas"]
            novo_v_atual = pool["valor_atual"] + fees_temp
            novas_reinv = pool["fees_reinvestidas"] + fees_temp
            update_pool_fees_db(
                pool["id"],
                novo_v_atual,
                pool["fees_sacadas"],
                novas_reinv,
                0.0,
            )
            st.success("Fees reinvestidas!")
            st.rerun()

        if col_b4.button(
            "💸 Sacar Fees",
            key=f"withdraw_{pool['id']}",
            use_container_width=True,
        ):
          if pool["fees_nao_coletadas"] > 0:
            fees_temp = pool["fees_nao_coletadas"]
            novas_sacadas = pool["fees_sacadas"] + fees_temp
            update_pool_fees_db(
                pool["id"],
                pool["valor_atual"],
                novas_sacadas,
                pool["fees_reinvestidas"],
                0.0,
            )
            st.success("Fees sacadas!")
            st.rerun()

        with col_b5:
          with st.popover("⚙️ Mais Opções", use_container_width=True):
            if st.button(
                "🔒 Fechar/Ativar Pool",
                key=f"close_{pool['id']}",
                use_container_width=True,
            ):
              novo_st = "Fechada" if pool["estado"] == "Ativa" else "Ativa"
              update_pool_status_db(pool["id"], novo_st)
              st.rerun()

            if st.button(
                "🗑️ Excluir Pool",
                key=f"del_{pool['id']}",
                use_container_width=True,
                type="primary",
            ):
              delete_pool_db(pool["id"])
              st.rerun()

        # GRÁFICO ANALÍTICO
        st.write(" ")
        col_g_title, col_g_btn = st.columns([2, 3])
        with col_g_title:
          st.markdown("##### 📈 Histórico de Performance")

        with col_g_btn:
          metric_choice = st.radio(
              "Métrica",
              options=["Liquidez ($)", "APR das Fees (%)"],
              horizontal=True,
              key=f"metric_choice_{pool['id']}",
              label_visibility="collapsed",
          )

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
          tendencia_liq = np.linspace(
              pool["valor_inicial"], pool["valor_atual"], num_pontos
          )
          simulated_liquidez = tendencia_liq + ruido_liq
          simulated_liquidez[-1] = pool["valor_atual"]

          dias_array = np.arange(1, num_pontos + 1)
          fees_progresso = np.linspace(0.1, total_fees_geradas_pool, num_pontos)
          simulated_apr = (
              (fees_progresso / pool["valor_inicial"])
              * (365 / dias_array)
              * 100
              if pool["valor_inicial"] > 0
              else np.zeros(num_pontos)
          )
          simulated_apr[-1] = apr_total

        df_full = pd.DataFrame({
            "Data": full_dates.date,
            "Liquidez ($)": simulated_liquidez,
            "APR das Fees (%)": simulated_apr,
        })

        df_chart = df_full[
            (df_full["Data"] >= dt_inicio_sel)
            & (df_full["Data"] <= dt_fim_sel)
        ]

        if metric_choice == "Liquidez ($)":
          y_col = "Liquidez ($)"
          line_color = "#10b981"
        else:
          y_col = "APR das Fees (%)"
          line_color = "#8b5cf6"

        fig = px.line(
            df_chart, x="Data", y=y_col, line_shape="spline", markers=True
        )
        fig.update_traces(line_color=line_color, line_width=2.5)
        fig.update_layout(
            template="plotly_dark",
            height=250,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="",
            yaxis_title="",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

        selected_range = st.slider(
            "Seleção de Intervalo",
            min_value=dt_entrada,
            max_value=dt_hoje,
            value=st.session_state[slider_key],
            format="YYYY-MM-DD",
            key=slider_key,
            label_visibility="collapsed",
        )

        st.markdown("---")
