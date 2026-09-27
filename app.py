import datetime
import sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------
# BASE DE DADOS SQLITE (PERSISTÊNCIA DE DADOS)
# -------------------------------------------------------------
DB_FILE = "pools_data.db"


def init_db():
  """Cria a tabela se não existir e insere a pool inicial caso esteja vazia."""
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
            data_entrada TEXT
        )
    """)
  conn.commit()

  # Se a base de dados estiver vazia, adiciona uma pool de demonstração (Pool #1)
  c.execute("SELECT COUNT(*) FROM pools")
  if c.fetchone()[0] == 0:
    c.execute(
        """
            INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees_sacadas, fees_reinvestidas, fees_nao_coletadas, range_min, range_max, data_entrada)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            19469.55,
            30933.15,
            "2026-08-20",
        ),
    )
    conn.commit()
  conn.close()


def load_pools():
  """Carrega todas as pools da base de dados SQLite."""
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute("SELECT * FROM pools ORDER BY id ASC")
  rows = c.fetchall()
  conn.close()

  pools = []
  for r in rows:
    # Tratamento da data
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
):
  """Adiciona uma nova pool à base de dados."""
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute(
      """
        INSERT INTO pools (par, rede, estado, valor_inicial, valor_atual, fees_sacadas, fees_reinvestidas, fees_nao_coletadas, range_min, range_max, data_entrada)
        VALUES (?, ?, 'Ativa', ?, ?, ?, ?, ?, ?, ?, ?)
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
      ),
  )
  conn.commit()
  conn.close()


def update_pool_db(pool_id, valor_atual, fees_pendentes, data_entrada):
  """Atualiza os dados de uma pool na base de dados."""
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute(
      """
        UPDATE pools 
        SET valor_atual = ?, fees_nao_coletadas = ?, data_entrada = ?
        WHERE id = ?
    """,
      (valor_atual, fees_pendentes, data_entrada.strftime("%Y-%m-%d"), pool_id),
  )
  conn.commit()
  conn.close()


def update_pool_status_db(pool_id, novo_estado):
  """Atualiza o estado (Ativa/Fechada) de uma pool."""
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute(
      "UPDATE pools SET estado = ? WHERE id = ?", (novo_estado, pool_id)
  )
  conn.commit()
  conn.close()


def update_pool_fees_db(pool_id, novo_v_atual, f_sac, f_reinv, f_pend):
  """Atualiza as fees e valor atual após saque ou reinvestimento."""
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
  """Elimina uma pool da base de dados."""
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute("DELETE FROM pools WHERE id = ?", (pool_id,))
  conn.commit()
  conn.close()


def clear_all_pools_db():
  """Elimina todas as pools da base de dados."""
  conn = sqlite3.connect(DB_FILE)
  c = conn.cursor()
  c.execute("DELETE FROM pools")
  conn.commit()
  conn.close()


# Inicializar Base de Dados
init_db()

# Estilo personalizado para os cartões e barra azul grossa
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

    /* ESTILO DA BARRA DE ROLAMENTO: AZUL E GROSSA */
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

# Carregar dados atualizados da base de dados
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


# Modal para atualizar pool
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

      nova_data_entrada = st.date_input("Data de Entrada", value=data_ori)

      submitted = st.form_submit_button(
          "Guardar Alterações", type="primary", use_container_width=True
      )

      if submitted:
        update_pool_db(
            pool_id, novo_valor_atual, novas_fees_pendentes, nova_data_entrada
        )
        st.success(f"Pool ({pool['par']}) atualizada com sucesso!")
        st.rerun()


# Painel Lateral - Adicionar Nova Pool
with st.sidebar:
  st.header("➕ Adicionar Nova Pool")

  with st.form("nova_pool_form", clear_on_submit=True):
    par = st.text_input("Par (ex: COIN/USDC)", key="form_par")
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
      )

      st.success("Pool adicionada e guardada com sucesso!")
      st.rerun()

  st.markdown("---")
  if st.button("🗑️ Limpar Todas as Pools"):
    clear_all_pools_db()
    st.rerun()

# -------------------------------------------------------------
# CÁLCULOS DO AGREGADO GERAL (TOPO)
# -------------------------------------------------------------
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

# EXIBIÇÃO DAS MÉTRICAS AGREGADAS NO TOPO
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
      "👁️ Mostrar Detalhes das Pools"
      if st.session_state.ocultar_detalhes
      else "🙈 Esconder Detalhes das Pools"
  )
  if st.button(label_btn, use_container_width=True):
    st.session_state.ocultar_detalhes = not st.session_state.ocultar_detalhes
    st.rerun()

st.markdown("---")

# Exibir Pools
if not pools_data:
  st.info(
      "Nenhuma piscina registada. Utiliza o painel lateral para adicionar."
  )
else:
  # SE A OPÇÃO DE ESCONDER DETALHES ESTIVER ATIVA: MOSTRA A TABELA DE RESUMO
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
          "Range Mín": f"{p['range_min']:,.2f}",
          "Range Máx": f"{p['range_max']:,.2f}",
      })
    df_resumo = pd.DataFrame(resumo_list)
    st.dataframe(df_resumo, use_container_width=True, hide_index=True)

  else:
    # MODO DETALHADO (COMPLETO)
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

      # Cartão Container
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

        # Blocos de métricas secundárias
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

        # Botões de Ação
        btn1, btn2, btn3, btn4, btn5 = st.columns(5)

        if btn1.button(f"✏️ Atualizar Pool", key=f"edit_{pool['id']}"):
          modal_atualizar_pool(pool["id"])

        if btn2.button(f"🔄 Reinvestir Fees", key=f"reinvest_{pool['id']}"):
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
            st.success(f"${fees_temp:,.2f} reinvestidos com sucesso!")
            st.rerun()
          else:
            st.warning("Não há fees pendentes para reinvestir.")

        if btn3.button(f"💸 Sacar Fees", key=f"withdraw_{pool['id']}"):
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
            st.success(f"${fees_temp:,.2f} sacados para a carteira!")
            st.rerun()
          else:
            st.warning("Não há fees pendentes para sacar.")

        if btn4.button(
            f"🔒 Fechar / Ativar", key=f"close_{pool['id']}"
        ):
          novo_st = "Fechada" if pool["estado"] == "Ativa" else "Ativa"
          update_pool_status_db(pool["id"], novo_st)
          st.rerun()

        if btn5.button(f"🗑️ Excluir", key=f"del_{pool['id']}"):
          delete_pool_db(pool["id"])
          st.rerun()

        # -------------------------------------------------------------
        # 1. GRÁFICO DE HISTÓRICO
        # -------------------------------------------------------------
        st.subheader("📈 Histórico de Liquidez")

        slider_key = f"slider_range_{pool['id']}"
        if slider_key not in st.session_state:
          st.session_state[slider_key] = (dt_entrada, dt_hoje)

        dt_inicio_sel, dt_fim_sel = st.session_state[slider_key]

        full_dates = pd.date_range(start=dt_entrada, end=dt_hoje, freq="D")
        num_pontos = len(full_dates)

        if num_pontos == 1:
          simulated_values = [pool["valor_atual"]]
        else:
          np.random.seed(pool["id"])
          ruido = np.cumsum(np.random.normal(0, 2, size=num_pontos))
          ruido = ruido - ruido[0]
          tendencia = np.linspace(
              pool["valor_inicial"], pool["valor_atual"], num_pontos
          )
          simulated_values = tendencia + ruido
          simulated_values[-1] = pool["valor_atual"]

        df_full = pd.DataFrame(
            {"Data": full_dates.date, "Liquidez ($)": simulated_values}
        )

        df_chart = df_full[
            (df_full["Data"] >= dt_inicio_sel)
            & (df_full["Data"] <= dt_fim_sel)
        ]

        fig = px.line(
            df_chart,
            x="Data",
            y="Liquidez ($)",
            line_shape="spline",
            markers=True,
        )
        fig.update_traces(line_color="#10b981", line_width=3)
        fig.update_layout(
            template="plotly_dark",
            height=250,
            margin=dict(l=20, r=20, t=10, b=10),
            xaxis_title="",
            yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

        # -------------------------------------------------------------
        # 2. BARRA DE ROLAMENTO
        # -------------------------------------------------------------
        st.write("🟦 **Ajuste o Intervalo de Datas para calcular o APR:**")
        selected_range = st.slider(
            "Seleção de Intervalo",
            min_value=dt_entrada,
            max_value=dt_hoje,
            value=st.session_state[slider_key],
            format="YYYY-MM-DD",
            key=slider_key,
            label_visibility="collapsed",
        )

        # -------------------------------------------------------------
        # 3. RESULTADOS DO APR
        # -------------------------------------------------------------
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
