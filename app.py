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
    .pool-card {
        background-color: #1e222d;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 25px;
        border: 1px solid #2a2e39;
    }
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

# Inicializar bases de dados na sessão
if "pools_data" not in st.session_state:
  st.session_state.pools_data = [
      {
          "id": 1,
          "par": "COIN / USDC",
          "rede": "BYREAL - SOL",
          "estado": "Ativa",
          "valor_inicial": 169.0,
          "valor_atual": 200.0,
          "fees_acumuladas": 21.97,
          "fees_nao_coletadas": 1.86,
          "range_min": 150.0,
          "range_max": 225.0,
          "data_entrada": datetime.date(2026, 6, 7),
      }
  ]

DEX_OPTIONS = [
    "Uniswap v3",
    "Raydium",
    "Orca",
    "Kamino",
    "PancakeSwap",
    "Curve",
    "Meteora",
    "Cetus",
    "Outro",
]

# Painel Lateral - Adicionar Nova Pool
with st.sidebar:
  st.header("➕ Adicionar Nova Pool")
  with st.form("nova_pool_form"):
    par = st.text_input("Par (ex: COIN/USDC)", "SOL/USDC")
    rede = st.text_input("Rede / Plataforma", "BYREAL - SOL")
    dex = st.selectbox("DEX", DEX_OPTIONS)
    v_init = st.number_input("Valor Inicial ($)", min_value=0.0, value=169.0)
    v_atual = st.number_input("Valor Atual ($)", min_value=0.0, value=200.0)
    fees_totais = st.number_input(
        "Total Fees Coletadas ($)", min_value=0.0, value=21.97
    )
    fees_pendentes = st.number_input(
        "Fees Acumuladas Pendentes ($)", min_value=0.0, value=1.86
    )
    col_r1, col_r2 = st.columns(2)
    r_min = col_r1.number_input("Range Mín ($)", value=150.0)
    r_max = col_r2.number_input("Range Máx ($)", value=225.0)
    data_in = st.date_input("Data de Entrada", datetime.date.today())

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
          "fees_acumuladas": fees_totais,
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

# Exibir Pools no formato de Cartões
if not st.session_state.pools_data:
  st.info(
      "Nenhuma piscina registada. Utiliza o painel lateral para adicionar."
  )
else:
  for pool in st.session_state.pools_data:
    # Cálculos
    dias_ativos = (datetime.date.today() - pool["data_entrada"]).days
    if dias_ativos <= 0:
      dias_ativos = 1

    pnl = (pool["valor_atual"] + pool["fees_acumuladas"]) - pool[
        "valor_inicial"
    ]
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
        (pool["fees_acumuladas"] / pool["valor_inicial"])
        * (365 / dias_ativos)
        * 100
        if pool["valor_inicial"] > 0
        else 0
    )

    # Cartão Container
    with st.container():
      # Cabeçalho do Cartão
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
        m5.metric("Fees Acum.", f"${pool['fees_nao_coletadas']:,.2f}")

      # Blocos de métricas secundárias
      b1, b2, b3, b4 = st.columns(4)
      b1.info(f"**Valor Inicial:** ${pool['valor_inicial']:,.2f}")
      b2.info(f"**Dias Ativos:** {dias_ativos} dias")
      b3.info(f"**Total Fees Coletadas:** ${pool['fees_acumuladas']:,.2f}")
      b4.info(
          f"**Range de Preço:** ${pool['range_min']:,.0f} -"
          f" ${pool['range_max']:,.0f}"
      )

      # Botões de Ação
      btn1, btn2, btn3, btn4 = st.columns(4)

      if btn1.button(f"✏️ Atualizar / Editar", key=f"edit_{pool['id']}"):
        st.toast(f"Editar Pool #{pool['id']} selecionado")

      if btn2.button(f"💵 Coletar Fees", key=f"fee_{pool['id']}"):
        pool["fees_acumuladas"] += pool["fees_nao_coletadas"]
        pool["fees_nao_coletadas"] = 0.0
        st.success("Fees coletadas e somadas ao total!")
        st.rerun()

      if btn3.button(
          f"🔒 Fechar / Alterar Estado", key=f"close_{pool['id']}"
      ):
        pool["estado"] = "Fechada" if pool["estado"] == "Ativa" else "Ativa"
        st.rerun()

      if btn4.button(f"🗑️ Excluir", key=f"del_{pool['id']}"):
        st.session_state.pools_data = [
            p for p in st.session_state.pools_data if p["id"] != pool["id"]
        ]
        st.rerun()

      # Gráfico de Histórico
      st.subheader("📈 Histórico de Liquidez")

      # Gerar dados simulados de histórico
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
