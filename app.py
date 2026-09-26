Criei a folha de cálculo no Google Sheets e preparei o código em Python com Streamlit para o teu dashboard interativo.

[Dashboard_Piscinas_Liquidez_Crypto](https://docs.google.com/spreadsheets/d/1jS9N_HHYTeIAE9fxpBrWKF48wrRK1n7aEEvsJZhHg9E/edit?usp=drivesdk&ouid=116299652542920536093&utm_source=gemini)


### Estrutura da Folha de Cálculo (Google Sheets)

Podes estruturar as colunas da tua folha de cálculo da seguinte forma:

1. **DEX / Protocolo** (ex.: Raydium, Uniswap v3, Orca)
2. **Par de Cripto** (ex.: SOL/USDC)
3. **Data de Entrada**
4. **Valor de Entrada ($)**
5. **Valor Atual / Levantamento ($)**
6. **Rendimentos de Fees / Rewards ($)**
7. **Lucro / Prejuízo Líquido ($)**: `= (E2 + F2) - D2`
8. **ROI (%)**: `= G2 / D2`

---

### Aplicação Interativa em Python (Streamlit)

Para executar esta aplicação localmente, instala as dependências (`pip install streamlit pandas`) e executa o comando `streamlit run app.py` com o seguinte código:

```python
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Dashboard Piscinas Liquidez", layout="wide"
)

st.title("📊 Dashboard de Control de Piscinas de Liquidez")

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
  protocolo = st.text_input("Protocolo", "Uniswap v3")
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

```
