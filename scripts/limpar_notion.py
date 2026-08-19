import os, re, json, urllib.request, sys, io

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 1. Carregar .env
env = {}
env_file = '.env' if os.path.exists('.env') else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

token = env.get('NOTION_TOKEN') or env.get('NOTION_API_KEY') or os.getenv('NOTION_TOKEN')
db_id = env.get('NOTION_DATABASE_ID') or env.get('DATABASE_ID') or os.getenv('NOTION_DATABASE_ID')

if not token or not db_id:
    print("Erro: NOTION_TOKEN ou NOTION_DATABASE_ID nao encontrados no .env")
    exit(1)

clean_db_id = db_id.replace('-', '')

headers = {
    'Authorization': f'Bearer {token}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

def clean_analysis_text(text: str) -> str:
    """Removes all emojis and repetitive prefix markers (e.g. 'Adequada (71%): Adequada:') returning clean natural text."""
    if not text:
        return ""
    # Remove all emojis
    cleaned = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]', '', text)
    pattern = r'^\s*(?:Adequada|Inadequada|Aprovada|Rejeitada(?:\s*por\s*IA)?|Filtro\s*Automático)?(?:\s*\([^)]*\))?\s*:\s*'
    for _ in range(5):
        new_cleaned = re.sub(pattern, '', cleaned, count=1, flags=re.IGNORECASE).strip()
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned
    cleaned = cleaned.strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned

def get_analise_prop_name(props):
    for name in props.keys():
        norm = name.lower().replace('á', 'a').replace('í', 'i').strip()
        if 'analise' in norm:
            return name
    return None

cursor = None
total_pages = 0
updated_count = 0

print("A ligar ao Notion e a limpar emojis e prefixos redundantes...")

while True:
    payload = {'start_cursor': cursor} if cursor else {}
    req = urllib.request.Request(
        f'https://api.notion.com/v1/databases/{clean_db_id}/query',
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"Erro na ligacao ao Notion: {e}")
        break

    pages = data.get('results', [])
    total_pages += len(pages)

    for page in pages:
        props = page.get('properties', {})
        prop_name = get_analise_prop_name(props)
        
        if not prop_name:
            continue
            
        analise_prop = props.get(prop_name, {}).get('rich_text', [])
        if not analise_prop:
            continue

        old_text = ''.join([t.get('plain_text', '') for t in analise_prop])
        new_text = clean_analysis_text(old_text)

        if new_text != old_text:
            update_payload = {
                'properties': {
                    prop_name: {
                        'rich_text': [{'text': {'content': new_text}}]
                    }
                }
            }
            update_req = urllib.request.Request(
                f'https://api.notion.com/v1/pages/{page["id"]}',
                data=json.dumps(update_payload).encode('utf-8'),
                headers=headers,
                method='PATCH'
            )
            with urllib.request.urlopen(update_req):
                pass
            
            title_prop = props.get('Title', {}).get('title', []) or props.get('Nome', {}).get('title', []) or props.get('Cargo', {}).get('title', []) or props.get('Name', {}).get('title', [])
            job_title = title_prop[0].get('plain_text', 'Vaga') if title_prop else 'Vaga'
            print(f"Atualizado [{job_title}]:")
            print(f"   De:   {old_text}")
            print(f"   Para: {new_text}\n")
            updated_count += 1

    if not data.get('has_more'):
        break
    cursor = data.get('next_cursor')

print(f"Total de paginas analisadas: {total_pages}")
print(f"Total de vagas limpas com sucesso: {updated_count}")
