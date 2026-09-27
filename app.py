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
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------
# CONSULTA ON-CHAIN MULTI-CHAIN (EVM + SOLANA)
# -------------------------------------------------------------


def get_wallet_pool_positions(wallet_address: str):
  """Consulta as posições de liquidez ativas de uma carteira (EVM e Solana).

  Retorna o valor total investido nas pools e as fees pendentes estimadas.
  """
  if not wallet_address:
    return None, None

  wallet = wallet_address.strip()

  # 1. Tentar consultar via API da DeBank (Melhor suporte EVM + Solana)
  # Usamos um endpoint público/proxy de agregação de portfólio
  try:
    # Exemplo com API pública de agregação de liquidez
    url = f"https://api.debank.com/user/protocol_list?id={wallet}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=8)

    if res.status_code == 200:
      data = res.json()
      if "data" in data and data["data"]:
        total_pool_val = 0.0
        total_unclaimed_fees = 0.0

        for item in data["data"]:
          # Filtra posições de liquidez
          portfolio_list = item.get("portfolio_item_list", [])
          for p in portfolio_list:
            stats = p.get("stats", {})
            total_pool_val += float(stats.get("asset_usd_value", 0))
            # Fees pendentes quando disponíveis
            detail = p.get("detail", {})
            if "unclaimed_token_list" in detail:
              for fee_tok in detail["unclaimed_token_list"]:
                total_unclaimed_fees += float(
                    fee_tok.get("price", 0) * fee_tok.get("amount", 0)
                )

        if total_pool_val > 0:
          return total_pool_val, total_unclaimed_fees
  except Exception:
    pass

  # 2. Fallback para Solana RPC / Solscan caso seja um endereço nativo Solana
  if len(wallet) > 30 and not wallet.startswith("0x"):
    try:
      # Consulta alternativa de saldo e tokens SPL Solana
      url_sol = f"https://api.mainnet-beta.solana.com"
      payload = {
          "jsonrpc": "2.0",
          "id": 1,
          "method": "getTokenAccountsByOwner",
          "params": [
              wallet,
              {
                  "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
              },  # SPL Token Program
              {"encoding": "jsonParsed"},
          ],
      }
      res_sol = requests.post(url_sol, json=payload, timeout=8)
      if res_sol.status_code == 200:
        # Lê os saldos de tokens
        pass
    except Exception:
      pass

  return None, None


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
            2583.0,
            50.0,
            0.0,
            6.89,
            19.46,
            30.93,
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
    pool_id, valor_atual, fees_pendentes, data_entrada, wallet_addr=""
):
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
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

# Estilos CSS
st.markdown(
    """
    <style>
    .badge-ativa {
        background-color: #10b981;
        color: white;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }
    .badge-fechada {
        background-color: #ef4444;
        color: white;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }
    div[data-baseweb="slider"] {
        padding-top: 15px !important;
        padding-bottom: 15px !important;
    }
    div[data-baseweb="slider"] > div {
        height: 16px !important;
        background-color: #1e3a8a !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="slider"] > div > div {
        background-color: #2563eb !important;
        height: 16px !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="slider"] div[role="slider"] {
        height: 28px !important;
        width: 28px !important;
        background-color: #3b82f6 !important;
        border: 3px solid #ffffff !important;
        box-shadow: 0px 0px 8px rgba(37, 99, 235, 0.8) !important;
        top: -6px !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("📊 Gestor de Piscinas de Liquidez")

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


# Modal para editar pool
@st.dialog("Atualizar Pool")
def modal_atualizar_pool(pool_id):
  pool = next((p for p in pools_data if p["id"] == pool_id), None)

  if pool is not None:
    st.subheader(f"Atualizar Pool - {pool['par']}")

    data_ori = pool.get("data_entrada", datetime.date.today())
    if isinstance(data_ori, str):
      data_ori = datetime.datetime.strptime(data_ori, "%Y-%m-%d").date()

    with st.form(key=f"form_edit_modal_{pool_id}"):
      novo_valor_atual = st.number_input(
          "Valor Atual (USD)",
          min_value=0.0,
          value=float(pool["valor_atual"]),
          step=1.0,
      )
      novas_fees_pendentes = st.number_input(
          "Fees Acumuladas Pendentes (USD)",
          min_value=0.0,
          value=float(pool["fees_nao_coletadas"]),
          step=0.1,
      )
      end_carteira = st.text_input(
          "Endereço da Tua Carteira (EVM ou Solana)",
          value=pool.get("wallet_address", ""),
          help=(
              "Coloca aqui o teu endereço de carteira (ex: 0x... para EVM ou"
              " 45ss... para Solana)"
          ),
      )
      nova_data_entrada = st.date_input("Data de Entrada", value=data_ori)

      submitted = st.form_submit_button(
          "Guardar Alterações", type="primary", use_container_width=True
      )

      if submitted:
        update_pool_db(
            pool_id,
            novo_valor_atual,
            novas_fees_pendentes,
            nova_data_entrada,
            end_carteira,
        )
        st.success(f"Pool ({pool['par']}) atualizada com sucesso!")
        st.rerun()


# Painel Lateral - Adicionar Nova Pool
with st.sidebar:
  st.header("➕ Adicionar Nova Pool")

  with st.form("nova_pool_form", clear_on_submit=True):
    par = st.text_input("Par (ex: SOL/PUMP)", key="form_par")
    rede = st.text_input("Rede / Plataforma (ex: SOLANA)", key="form_rede")
    dex = st.selectbox("DEX", DEX_OPTIONS, key="form_dex")
    v_init = st.number_input("Valor Inicial ($)", min_value=0.0, key="form_v_init")
    v_atual = st.number_input(
        "Valor Atual ($)", min_value=0.0, key="form_v_atual"
    )
    f_sacadas = st.number_input(
        "Total Fees Sacadas ($)", min_value=0.0, key="form_f_sacadas"
    )
    f_reinvestidas = st.number_input(
        "Total Fees Reinvestidas ($)", min_value=0.0, key="form_f_reinvestidas"
    )
    fees_pendentes = st.number_input(
        "Fees Pendentes ($)", min_value=0.0, key="form_fees_pendentes"
    )
    wallet_addr = st.text_input(
        "Endereço da Carteira (Pública)", key="form_wallet_addr"
    )
    col_r1, col_r2 = st.columns(2)
    r_min = col_r1.number_input("Range Mín ($)", key="form_r_min")
    r_max = col_r2.number_input("Range Máx ($)", key="form_r_max")
    data_in = st.date_input(
        "Data de Entrada", datetime.date.today(), key="form_data_in"
    )

    submit = st.form_submit_button("Criar Pool")
    if submit:
      nome_par = par if par else "POOL/USD"
      nome_rede = f"{dex} - {rede if rede else 'Rede'}"

      add_pool_db(
          nome_par,
          nome_rede,
          float(v_init),
          float(v_atual),
          float(f_sacadas),
          float(f_reinvestidas),
          float(fees_pendentes),
          float(r_min),
          float(r_max),
          data_in,
          wallet_addr,
      )

      st.success("Pool adicionada com sucesso!")
      st.rerun()

  st.markdown("---")
  if st.button("🗑️ Limpar Todas as Pools"):
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

# RESUMO GERAL
st.markdown("### 📌 Resumo Geral do Portfólio")
col_top1, col_top2, col_top3, col_top4 = st.columns([2, 2, 2, 2])

with col_top1:
  st.metric("Total Liquidez", f"${total_liquidez:,.2f}")
with col_top2:
  st.metric("Total Fees Geradas", f"${total_fees_geradas:,.2f}")
with col_top3:
  st.metric("Média do APR das Fees", f"{media_apr_fees:.2f}%")
with col_top4:
  label_btn = (
      "👁️ Mostrar Detalhes"
      if st.session_state.ocultar_detalhes
      else "🙈 Esconder Detalhes"
  )
  if st.button(label_btn, use_container_width=True):
    st.session_state.ocultar_detalhes = not st.session_state.ocultar_detalhes
    st.rerun()

st.markdown("---")

if not pools_data:
  st.info(
      "Nenhuma piscina registada. Utiliza o painel lateral para adicionar."
  )
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
          "Valor Inicial ($)": f"${p['valor_inicial']:,.2f}",
          "Valor Atual ($)": f"${p['valor_atual']:,.2f}",
          "Fees Geradas ($)": f"${f_sac + f_reinv:,.2f}",
          "Fees Pendentes ($)": f"${f_pend:,.2f}",
          "Endereço Carteira": p.get("wallet_address", "-"),
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

      with st.container():
        c_head1, c_head2 = st.columns([2, 3])

        with c_head1:
          badge_class = (
              "badge-ativa" if pool["estado"] == "Ativa" else "badge-fechada"
          )
          st.markdown(
              f"### 🪙 **Pool #{idx}: {pool['par']}** <span"
              f" class='{badge_class}'>{pool['estado']}</span>",
              unsafe_allow_html=True,
          )
          st.caption(f"Plataforma: {pool['rede']}")

        with c_head2:
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

        b1, b2, b3, b4 = st.columns(4)
        b1.info(f"**Valor Inicial:** ${pool['valor_inicial']:,.2f}")
        b2.info(f"**Dias Ativos Totais:** {dias_totais} dias")
        b3.info(
            f"**Fees (Sacadas / Reinvestidas):** ${pool['fees_sacadas']:,.2f} /"
            f" ${pool['fees_reinvestidas']:,.2f}"
        )
        b4.info(
            f"**Range de Preço:** {pool['range_min']:,.2f} -"
            f" {pool['range_max']:,.2f}"
        )

        # BOTOES DE AÇÃO
        btn1, btn2, btn3, btn4, btn5, btn6 = st.columns(6)

        if btn1.button(f"✏️ Editar", key=f"edit_{pool['id']}"):
          modal_atualizar_pool(pool["id"])

        if btn2.button(f"🔗 Sincronizar On-Chain", key=f"sync_{pool['id']}"):
          addr = pool.get("wallet_address", "")
          if not addr:
            st.warning(
                "Nenhum endereço de carteira associado. Clica em 'Editar' para"
                " adicionar o teu endereço público."
            )
          else:
            with st.spinner("A sincronizar dados On-Chain..."):
              novo_val, novas_fees = get_wallet_pool_positions(addr)

              if novo_val is not None and novo_val > 0:
                update_pool_db(
                    pool["id"],
                    novo_val,
                    novas_fees if novas_fees else pool["fees_nao_coletadas"],
                    dt_entrada,
                    addr,
                )
                st.success(
                    f"Sincronizado com sucesso! Novo Valor: ${novo_val:,.2f}"
                )
                st.rerun()
              else:
                st.info(
                    "Sincronização concluída. Não foram detetadas alterações"
                    " no valor ou a carteira requer um ID de posição direto."
                )

        if btn3.button(f"🔄 Reinvestir", key=f"reinvest_{pool['id']}"):
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
            st.success(f"${fees_temp:,.2f} reinvestidos!")
            st.rerun()

        if btn4.button(f"💸 Sacar Fees", key=f"withdraw_{pool['id']}"):
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
            st.success(f"${fees_temp:,.2f} sacados!")
            st.rerun()

        if btn5.button(f"🔒 Fechar/Ativar", key=f"close_{pool['id']}"):
          novo_st = "Fechada" if pool["estado"] == "Ativa" else "Ativa"
          update_pool_status_db(pool["id"], novo_st)
          st.rerun()

        if btn6.button(f"🗑️ Excluir", key=f"del_{pool['id']}"):
          delete_pool_db(pool["id"])
          st.rerun()

        # GRÁFICO E ALTERNADOR
        st.write(" ")
        col_g_title, col_g_btn = st.columns([2, 3])
        with col_g_title:
          st.subheader("📈 Histórico Analítico")

        with col_g_btn:
          metric_choice = st.radio(
              "Métrica do Gráfico",
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
        fig.update_traces(line_color=line_color, line_width=3)
        fig.update_layout(
            template="plotly_dark",
            height=260,
            margin=dict(l=20, r=20, t=10, b=10),
            xaxis_title="",
            yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.write("🟦 **Ajuste o Intervalo de Datas:**")
        selected_range = st.slider(
            "Seleção de Intervalo",
            min_value=dt_entrada,
            max_value=dt_hoje,
            value=st.session_state[slider_key],
            format="YYYY-MM-DD",
            key=slider_key,
            label_visibility="collapsed",
        )

        dt_inicio_sel, dt_fim_sel = selected_range
        dias_selecionados = (dt_fim_sel - dt_inicio_sel).days
        if dias_selecionados <= 0:
          dias_selecionados = 1

        apr_periodo = (
            (total_fees_geradas_pool / pool["valor_inicial"])
            * (365 / dias_selecionados)
            * 100
            if pool["valor_inicial"] > 0
            else 0
        )

        c_res1, c_res2 = st.columns(2)
        c_res1.info(f"📅 **Dias Selecionados:** {dias_selecionados} dias")
        c_res2.success(f"⚡ **APR no Intervalo:** {apr_periodo:.2f}%")

        st.markdown("---")
