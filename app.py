import os
import time
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Gestor de Piscinas de Liquidez",
    page_icon="⚡",
    layout="wide"
)

# Credenciais do Supabase via Streamlit Secrets ou Variáveis de Ambiente
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", "")).strip().rstrip("/")
if SUPABASE_URL and not SUPABASE_URL.startswith("http"):
    SUPABASE_URL = f"https://{SUPABASE_URL}"

SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", "")).strip()

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -----------------------------------------------------------------------------
# 2. FUNÇÕES DE SUPORTE (API & SUPABASE)
# -----------------------------------------------------------------------------
def fetch_dexscreener_data(pair_address):
    """Obtém preço atual via DexScreener usando o Pair Address."""
    if not pair_address or len(str(pair_address).strip()) < 5:
        return None, None
    url = f"https://api.dexscreener.com/latest/dex/search?q={str(pair_address).strip()}"
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data and "pairs" in data and len(data["pairs"]) > 0:
                pair = data["pairs"][0]
                return float(pair.get("priceUsd", 0)), float(pair.get("priceNative", 0))
    except Exception as e:
        st.error(f"Erro ao consultar DexScreener: {e}")
    return None, None

def get_pools():
    """Lê todas as pools da base de dados Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/pools?select=*&order=id.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Erro ao carregar pools: {e}")
    return []

def get_historico_pnl():
    """Lê a tabela historico_pnl para desenhar os gráficos."""
    url = f"{SUPABASE_URL}/rest/v1/historico_pnl?select=*&order=data.asc"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def to_float(val, default=0.0):
    """Converte valores com segurança para float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# -----------------------------------------------------------------------------
# 3. INTERFACE PRINCIPAL & CABEÇALHO
# -----------------------------------------------------------------------------
st.title("⚡ Gestor de Piscinas de Liquidez (DeFi Dashboard)")

pools = get_pools()

# Processamento e conversão de dados das pools
total_investido = 0.0
total_valor_atual = 0.0

for p in pools:
    v_inv = to_float(p.get("valor_investido"))
    qtd = to_float(p.get("quantidade"))
    p_usd = to_float(p.get("preco_atual"))
    
    total_investido += v_inv
    
    if qtd > 0 and p_usd > 0:
        total_valor_atual += (qtd * p_usd)
    else:
        total_valor_atual += v_inv

pnl_global = total_valor_atual - total_investido
roi_global = (pnl_global / total_investido * 100) if total_investido > 0 else 0.0

# Exibição dos Cartões Principais
col1, col2, col3, col4 = st.columns(4)
col1.metric("Investimento Total", f"${total_investido:,.2f}")
col2.metric("Valor Atual Estimado", f"${total_valor_atual:,.2f}")
col3.metric("PnL Total ($)", f"${pnl_global:,.2f}", delta=f"{pnl_global:,.2f}")
col4.metric("ROI Acumulado (%)", f"{roi_global:.2f}%", delta=f"{roi_global:.2f}%")

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. BOTÃO DE SINCRONIZAÇÃO
# -----------------------------------------------------------------------------
col_sync, _ = st.columns([1, 3])
with col_sync:
    if st.button("🔗 Sincronizar Preços Agora", use_container_width=True):
        with st.spinner("A atualizar preços e estados das pools..."):
            for p in pools:
                addr = p.get("wallet_address")
                if addr:
                    p_usd, p_nat = fetch_dexscreener_data(addr)
                    if p_nat is not None:
                        r_min = to_float(p.get("range_min"))
                        r_max = to_float(p.get("range_max"))
                        
                        in_range = True
                        if r_min > 0 and p_nat < r_min:
                            in_range = False
                        elif r_max > 0 and p_nat > r_max:
                            in_range = False
                        
                        novo_estado = "Ativa" if in_range else "Inativa"
                        
                        patch_url = f"{SUPABASE_URL}/rest/v1/pools?id=eq.{p['id']}"
                        patch_data = {
                            "preco_atual": p_usd,Quando o dashboard do **Kamino Finance** (ou de outro protocolo em Solana/DeFi) fica "incompleto" — mostrando apenas a lista geral de pools e omitindo as tuas posições, os totais do teu portfólio ou os valores atualizados —, isso é quase sempre um problema de comunicação entre a interface do site e os nós da rede (**RPC nodes**), e não uma perda dos teus fundos.

Segue estes passos pela ordem recomendada para resolver e recarregar os dados:

### 1. Limpar a Cache do RPC e Forçar Atualização
A interface do Kamino guarda em cache as leituras da blockchain. Se o nó RPC que está a ser utilizado falhar, a página carrega a estrutura base, mas não puxa as tuas posições.

* **Hard Refresh:** Pressiona `Ctrl + F5` (Windows/Linux) ou `Cmd + Shift + R` (Mac) na página para ignorar a cache local.
* **Desconectar e Reconectar a Carteira:** Clica no teu endereço de carteira no canto superior direito, seleciona **Disconnect**, aguarda 5 segundos e volta a ligar (**Connect**).

### 2. Mudar o Nó RPC na Carteira (Phantom / Backpack / Solflare)
Se o nó predefinido da tua carteira estiver com *rate-limit* (bloqueio temporário por excesso de pedidos), o Kamino não consegue ler as tuas contas de liquidez.

* Na **Phantom**: Vai a **Definições (Ícone da engrenagem)** $\rightarrow$ **Definições do Developer** $\rightarrow$ **Nó RPC** e altera para outra opção (por exemplo, Triton, Helius ou QuickNode, se disponíveis).
* Recarrega a página do Kamino após mudar.

### 3. Verificar o Estado na Blockchain (Confirmação dos Fundos)
Para teres a certeza de que a posição continua intacta na rede enquanto a interface do site recupera:

1. Copia o endereço da tua carteira.
2. Acede a um explorador de DeFi em Solana, como o [Step Finance](https://www.step.finance) ou [Sonala Explorer / Solscan](https://solscan.io).
3. Cola o teu endereço. Estes exploradores leem diretamente os *program accounts* da Solana e mostrarão as tuas posições em Kamino ativas, mesmo que o site oficial esteja a passar por um *glitch* visual.

### 4. Limpeza de Navegador e Extensões
* **Testa em Janela Anónima:** Abre o navegador em modo privado, acede ao Kamino e liga a carteira. Se funcionar, é um indicador de que alguma extensão (ex.: adblockers, VPNs) ou a cache acumulada do navegador está a bloquear as chamadas API do Kamino.
* Se usares **Brave Browser** ou adblockers agressivos (uBlock Origin), experimenta desativar temporariamente a proteção para o domínio do Kamino.

---

<ElicitationsGroup message="Como pretendes dar seguimento?">
  <Elicitation label="Verificar posições diretamente via Solscan / Step Finance" query="Como posso verificar a minha posição do Kamino no Solscan para confirmar que os fundos estão seguros?" />
  <Elicitation label="Ajuda a alterar o nó RPC na carteira Phantom" query="Passo a passo detalhado para alterar o nó RPC na Phantom e resolver problemas de sincronização." />
</ElicitationsGroup>
