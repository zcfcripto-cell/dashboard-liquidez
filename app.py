import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Gestor de Piscinas de Liquidez", layout="wide")

# Estilo personalizado para os cartões
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
    </style>
""",
    unsafe_allow_html=True,
)

st.title("📊 Gestor de Piscinas de Liquidez")

# Inicializar bases de dados na sessão com os novos dados padrão da pool SOL/PUMP
if "pools_data" not in st.session_state:
  st.session_state.pools_data = [
      {
          "id": 1,
          "par": "SOL/PUMP",
          "rede": "Raydium - SOLANA",
          "estado": "Ativa",
          "valor_inicial": 2203.0,
          "valor_atual": 2583.0,
          "fees_sacadas": 50.0,
          "fees_reinvestidas": 0.0,
          "fees_nao_coletadas": 6.89,
          "range_min": 19469.55,
          "range_max": 30933.15,
          "data_entrada": datetime.date(2026, 9, 24),
      }
  ]

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


# Pop-up modal dinâmico com campo para atualizar a Data de Entrada
@st.dialog("Atualizar Pool")
def modal_atualizar_pool(pool_id):
  pool = next(
      (p for p in st.session_state.pools_data if p["id"] == pool_id), None
  )
  if pool:
    st.subheader(f"Atualizar Pool - {pool['par']}")

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
    nova_data_entrada = st.date_input(
        "Data de Entrada",
        value=pool.get("data_entrada", datetime.date.today()),
    )

    col_cancel, col_save = st.columns(2)
    if col_save.button("Salvar", type="primary", use_container_width=True):
      pool["valor_atual"] = novo_valor_atual
      pool["fees_nao_coletadas"] = novas_fees_pendentes
      pool["data_entrada"] = nova_data_entrada
      st.success(f"Pool {pool['par']} atualizada com sucesso!")
      st.rerun()

    if col_cancel.button("Cancelar", use_container_width=True):
      st.rerun()


# Painel Lateral - Adicionar Nova Pool
with st.sidebar:
  st.header("➕ Adicionar Nova Pool")
  with st.form("nova_pool_form"):
    par = st.text_input("Par (ex: COIN/USDC)", "SOL/PUMP")
    rede = st.text_input("Rede / Plataforma", "SOLANA")
    dex = st.selectbox("DEX", DEX_OPTIONS)
    v_init = st.number_input("Valor Inicial ($)", min_value=0.0, value=2203.0)
    v_atual = st.number_input("Valor Atual ($)", min_value=0.0, value=2583.0)
    f_sacadas = st.number_input(
        "Total Fees Sacadas ($)", min_value=0.0, value=50.0
    )
    f_reinvestidas = st.number_input(
        "Total Fees Reinvestidas ($)", min_value=0.0, value=0.0
    )
    fees_pendentes = st.number_input(
        "Fees Pendentes ($)", min_value=0.0, value=6.89
    )
    col_r1, col_r2 = st.columns(2)
    r_min = col_r1.number_input("Range Mín ($)", value=19469.55)
    r_max = col_r2.number_input("Range Máx ($)", value=30933.15)
    data_in = st.date_input("Data de Entrada", datetime.date(2026, 9, 24))

    submit = st.form_submit_button("Criar Pool")
    if submit:
      novo_id = (
          max([p["id"] for p in st.session_state.pools_data], default=0) + 1
      )
      st.session_state.pools_data.append({
          "id": novo_id,
          "par": par,
          "rede": f"{dex} - {rede}",
          "estado": "Ativa",
          "valor_inicial": v_init,
          "valor_atual": v_atual,
          "fees_sacadas": f_sacadas,
          "fees_reinvestidas": f_reinvestidas,
          "fees_nao_coletadas": fees_pendentes,
          "range_min": r_min,
          "range_max": r_max,
          "data_entrada": data_in,
      })
      st.success("Pool adicionada com sucesso!")
      st.rerun()

  st.markdown("---")
  if st.button("🗑️ Limpar Todas as Pools"):
    st.session_state.pools_data = []
    st.rerun()

# Exibir Pools
if not st.session_state.pools_data:
  st.info(
      "Nenhuma piscina registada. Utiliza o painel lateral para adicionar."
  )
else:
  for pool in st.session_state.pools_data:
    # Garantir compatibilidade
    if "fees_sacadas" not in pool:
      pool["fees_sacadas"] = pool.get("fees_acumuladas", 0.0)
    if "fees_reinvestidas" not in pool:
      pool["fees_reinvestidas"] = 0.0

    # Cálculos
    dias_ativos = (datetime.date.today() - pool["data_entrada"]).days
    if dias_ativos <= 0:
      dias_ativos = 1

    total_fees_geradas = (
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

    apr = (
        (total_fees_geradas / pool["valor_inicial"])
        * (365 / dias_ativos)
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
            f"### 🪙 **{pool['par']}** <span class='{badge_class}'>{pool['estado']}</span>",
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
        m4.metric("APR Est.", f"{apr:.2f}%")
        m5.metric("Fees Pendentes", f"${pool['fees_nao_coletadas']:,.2f}")

      # Blocos de métricas secundárias
      b1, b2, b3, b4 = st.columns(4)
      b1.info(f"**Valor Inicial:** ${pool['valor_inicial']:,.2f}")
      b2.info(f"**Dias Ativos:** {dias_ativos} dias")
      b3.info(
          f"**Fees (Sacadas / Reinvestidas):** ${pool['fees_sacadas']:,.2f} /"
          f" ${pool['fees_reinvestidas']:,.2f}"
      )
      b4.info(
          f"**Range de Preço:** {pool['range_min']:,.2f} - {pool['range_max']:,.2f}"
      )

      # Botões de Ação
      btn1, btn2, btn3, btn4, btn5 = st.columns(5)

      if btn1.button(f"✏️ Atualizar Pool", key=f"edit_{pool['id']}"):
        modal_atualizar_pool(pool["id"])

      if btn2.button(f"🔄 Reinvestir Fees", key=f"reinvest_{pool['id']}"):
        if pool["fees_nao_coletadas"] > 0:
          fees_temp = pool["fees_nao_coletadas"]
          pool["valor_atual"] += fees_temp
          pool["fees_reinvestidas"] += fees_temp
          pool["fees_nao_coletadas"] = 0.0
          st.success(f"${fees_temp:,.2f} reinvestidos com sucesso!")
          st.rerun()
        else:
          st.warning("Não há fees pendentes para reinvestir.")

      if btn3.button(f"💸 Sacar Fees", key=f"withdraw_{pool['id']}"):
        if pool["fees_nao_coletadas"] > 0:
          fees_temp = pool["fees_nao_coletadas"]
          pool["fees_sacadas"] += fees_temp
          pool["fees_nao_coletadas"] = 0.0
          st.success(f"${fees_temp:,.2f} sacados para a carteira!")
          st.rerun()
        else:
          st.warning("Não há fees pendentes para sacar.")

      if btn4.button(
          f"🔒 Fechar / Ativar", key=f"close_{pool['id']}"
      ):
        pool["estado"] = "Fechada" if pool["estado"] == "Ativa" else "Ativa"
        st.rerun()

      if btn5.button(f"🗑️ Excluir", key=f"del_{pool['id']}"):
        st.session_state.pools_data = [
            p for p in st.session_state.pools_data if p["id"] != pool["id"]
        ]
        st.rerun()

      # Gráfico de Histórico
      st.subheader("📈 Histórico de Liquidez")

      dates = pd.date_range(end=datetime.datetime.now(), periods=15, freq="D")
      val_base = pool["valor_inicial"]
      np.random.seed(pool["id"])
      simulated_values = val_base + np.cumsum(
          np.random.normal(1.5, 3, size=15)
      )

      df_chart = pd.DataFrame({"Data": dates, "Liquidez ($)": simulated_values})

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
          margin=dict(l=20, r=20, t=20, b=20),
          xaxis_title="",
          yaxis_title="",
      )
      st.plotly_chart(fig, use_container_width=True)

      st.markdown("---")
