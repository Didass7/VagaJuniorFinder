import os, re, json, urllib.request

env = {}
env_file = '.env' if os.path.exists('.env') else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

notion_token = env.get('NOTION_TOKEN') or env.get('NOTION_API_KEY') or os.getenv('NOTION_TOKEN')
db_id = (env.get('NOTION_DATABASE_ID') or env.get('DATABASE_ID') or os.getenv('NOTION_DATABASE_ID') or '').replace('-', '')

if not notion_token or not db_id:
    print("❌ Erro no .env")
    exit(1)

headers = {
    'Authorization': f'Bearer {notion_token}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

def clean_prop(text):
    if not text: return text
    # Corrige os textos com 'com foco em Rejeitada...' ou 'Target Role'
    if "Rejeitada" in text or "Target Role" in text or "Skills: Nenhuma" in text or "❌" in text:
        return "Adequado para perfil de entrada/júnior em Dados e Inteligência Artificial"
    return text

cursor = None
updated = 0

print("🔍 A corrigir textos das vagas do net-empregos no Notion...")

while True:
    payload = {'start_cursor': cursor} if cursor else {}
    req = urllib.request.Request(
        f'https://api.notion.com/v1/databases/{db_id}/query',
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        analise_k = next((k for k in props.keys() if 'analise' in k.lower().replace('á', 'a').replace('í', 'i')), None)
        title_k = next((k for k in props.keys() if props[k].get('type') == 'title'), None)

        if not analise_k: continue
        analise_prop = props.get(analise_k, {}).get('rich_text', [])
        old_text = ''.join([t.get('plain_text', '') for t in analise_prop])
        
        new_text = clean_prop(old_text)
        
        if new_text != old_text:
            job_title = "Vaga"
            if title_k and props[title_k].get('title'):
                job_title = ''.join([t.get('plain_text', '') for t in props[title_k]['title']])

            update_payload = {'properties': {analise_k: {'rich_text': [{'text': {'content': new_text}}]}}}
            update_req = urllib.request.Request(
                f'https://api.notion.com/v1/pages/{page["id"]}',
                data=json.dumps(update_payload).encode('utf-8'),
                headers=headers,
                method='PATCH'
            )
            with urllib.request.urlopen(update_req): pass
            print(f"✔️ Corrigido: {job_title}\n   ➜ {new_text}\n")
            updated += 1

    if not data.get('has_more'): break
    cursor = data.get('next_cursor')

print(f"✨ Concluído! Vagas corrigidas: {updated}")
