import os
import requests
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Erro: Credenciais do Supabase não encontradas!")
    exit(1)

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# 1. Procurar as pools
url_pools = f"{SUPABASE_URL}/rest/v1/pools?select=*"
res_pools = requests.get(url_pools, headers=headers)

if res_pools.status_code != 200:
    print(f"❌ Erro ao procurar pools: {res_pools.text}")
    exit(1)

pools = res_pools.json()

# 2. Calcular o valor total apenas de pools abertas
valor_total = 0.0
for p in pools:
    if str(p.get("estado", "")).strip().lower() not in ["fechada", "closed"]:
        v_at = float(p.get("valor_atual") or p.get("valor_inicial") or 0)
        v_fees = float(p.get("fees") or 0)
        valor_total += (v_at + v_fees)

# 3. Guardar snapshot no historico_pnl
hoje = datetime.now().strftime('%Y-%m-%d')
payload = {
    "data": hoje,
    "valor_total_usd": round(valor_total, 2)
}

url_pnl = f"{SUPABASE_URL}/rest/v1/historico_pnl"
res_pnl = requests.post(url_pnl, headers=headers, json=payload)

if res_pnl.status_code in [200, 201]:
    print(f"✅ Snapshot diário gravado com sucesso para {hoje}: ${valor_total:,.2f}")
else:
    print(f"⚠️ Nota ao gravar snapshot: {res_pnl.text}")
