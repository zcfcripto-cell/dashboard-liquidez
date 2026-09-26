import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dashboard Piscinas Liquidez", layout="wide")

st.title("📊 Dashboard de Controlo de Piscinas de Liquidez")

# Lista de DEXs/Protocolos populares
DEX_OPTIONS = [
    "Uniswap v3",
    "Raydium",
    "Orca",
    "Kamino",
    "PancakeSwap",
    "Curve",
    "Aerodrome",
    "Meteora",
    "Trader Joe",
    "Outro (Introduzir manualmente)",
]

if "pools" not in st.session_state:
  st.session_state.pools = pd.DataFrame(
      columns=[
          "Protocolo",
          "Par",
          "Valor Entrada ($)",
          "Valor Saída/Atual ($)",
          "Fees Geradas ($)",
          "Lucro/Prejuízo ($)",
          "ROI (%)",
      ]
  )

with st.sidebar.form("nova_pool"):
  st.header("Adicionar / Atualizar Pool")

  # Caixa de seleção para Protocolo/DEX
  protocolo_selecionado = st.selectbox("Protocolo / DEX", DEX_OPTIONS)

  if protocolo_selecionado == "Outro (Introduzir manualmente)":
    protocolo = st.text_input("Nome do Protocolo", "Minha DEX Custom")
  else:
    protocolo = protocolo_selecionado

  par = st.text_input("Par de Cripto", "ETH / USDC")
  v_entrada = st.number_input("Valor de Entrada ($)", min_value=0.0, value=1000.0)
  v_saida = st.number_input("Valor Atual ou Saída ($)", min_value=0.0, value=1050.0)
  fees = st.number_input("Fees Recolhidas ($)", min_value=0.0, value=25.0)

  submitted = st.form_submit_button("Guardar Registo")
  if submitted:
    pnl = (v_saida + fees) - v_entrada
    roi = (pnl / v_entrada * 100) if v_entrada > 0 else 0.0
    nova_linha = {
        "Protocolo": protocolo,
        "Par": par,
        "Valor Entrada ($)": v_entrada,
        "Valor Saída/Atual ($)": v_saida,
        "Fees Geradas ($)": fees,
        "Lucro/Prejuízo ($)": round(pnl, 2),
        "ROI (%)": round(roi, 2),
    }
    st.session_state.pools = pd.concat(
        [st.session_state.pools, pd.DataFrame([nova_linha])], ignore_index=True
    )

if not st.session_state.pools.empty:
  df = st.session_state.pools
  col1, col2, col3 = st.columns(3)
  col1.metric("Total Investido", f"${df['Valor Entrada ($)'].sum():,.2f}")
  col2.metric("Total Fees Acumuladas", f"${df['Fees Geradas ($)'].sum():,.2f}")
  col3.metric("PnL Total Líquido", f"${df['Lucro/Prejuízo ($)'].sum():,.2f}")

  st.subheader("Posições Registadas")
  st.dataframe(df, use_container_width=True)
else:
  st.info("Nenhuma posição inserida. Utiliza o painel lateral para adicionar.")
