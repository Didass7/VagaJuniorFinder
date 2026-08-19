import os, re, json, time, urllib.request

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

notion_token = env.get('NOTION_TOKEN') or env.get('NOTION_API_KEY') or os.getenv('NOTION_TOKEN')
db_id = (env.get('NOTION_DATABASE_ID') or env.get('DATABASE_ID') or os.getenv('NOTION_DATABASE_ID') or '').replace('-', '')
gemini_key = env.get('GEMINI_API_KEY') or env.get('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')

if not notion_token or not db_id:
    print("❌ Erro: NOTION_TOKEN ou NOTION_DATABASE_ID não encontrados no .env")
    exit(1)

notion_headers = {
    'Authorization': f'Bearer {notion_token}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

def call_gemini(title, company, details):
    if not gemini_key:
        return None
    
    prompt = f"""
És um avaliador de vagas de emprego para um perfil Júnior de Engenharia de Dados e Inteligência Artificial / Data Science em Portugal.
Perfil do candidato: Júnior / Trainee em Data Engineering, AI/ML, Python, SQL, LangChain, RAG, Cloud.

Avalia a seguinte vaga:
Título: {title}
Empresa: {company}
Detalhes/Keywords: {details}

Retorna EXCLUSIVAMENTE um objeto JSON válido no formato:
{{
  "score": 72.5,
  "justificativa": "Breve frase explicando a adequação para júnior com esta stack"
}}
O valor 'score' deve ser um float entre 60.0 e 85.0 (ou 0 se for sénior/inadequada).
A 'justificativa' NÃO deve incluir a palavra 'Adequada' nem percentagens, apenas a explicação direta.
"""
    models = ['gemini-2.0-flash', 'gemini-1.5-flash']
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
        }
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                text = data['candidates'][0]['content']['parts'][0]['text']
                # Limpa markdown se vier com ```json
                text = re.sub(r'```json\s*|\s*```', '', text).strip()
                return json.loads(text)
        except Exception:
            continue
    return None

def fallback_score(title, details):
    # Cálculo heurístico calibrado se a API não estiver disponível
    score = 65.0
    techs = [t.strip() for t in details.replace('(', '').replace(')', '').split(',') if t.strip()]
    score += min(len(techs) * 3.5, 15.0)
    
    title_lower = title.lower()
    if 'engineer' in title_lower or 'developer' in title_lower or 'scientist' in title_lower:
        score += 2.5
    
    clean_details = details.replace('Avaliação Heurística:', '').replace('Vaga adequada para perfil Júnior', '').strip(' ():')
    just = f"Adequado para nível júnior com foco em {clean_details}" if clean_details else "Adequado para perfil júnior na área de dados/IA"
    return {"score": round(score, 1), "justificativa": just}

def get_prop_names(props):
    analise_name = None
    match_name = None
    title_name = None
    empresa_name = None

    for k, v in props.items():
        norm = k.lower().replace('á', 'a').replace('í', 'i').strip()
        v_type = v.get('type')
        if 'analise' in norm:
            analise_name = k
        elif 'match' in norm or v_type == 'number':
            match_name = k
        elif v_type == 'title':
            title_name = k
        elif 'empresa' in norm or 'company' in norm:
            empresa_name = k

    return analise_name, match_name, title_name, empresa_name

print("🔍 A pesquisar todas as vagas com 'Avaliação Heurística' ou Match a 0...")

cursor = None
updated = 0

while True:
    payload = {'start_cursor': cursor} if cursor else {}
    req = urllib.request.Request(
        f'https://api.notion.com/v1/databases/{db_id}/query',
        data=json.dumps(payload).encode('utf-8'),
        headers=notion_headers,
        method='POST'
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        analise_k, match_k, title_k, empresa_k = get_prop_names(props)
        
        if not analise_k or not match_k:
            continue
            
        analise_prop = props.get(analise_k, {}).get('rich_text', [])
        analise_text = ''.join([t.get('plain_text', '') for t in analise_prop])
        
        match_val = props.get(match_k, {}).get('number')
        if match_val is None:
            match_val = 0
            
        # Verifica se é uma das vagas que precisa de avaliação
        is_heuristic = "Avaliação Heurística" in analise_text or "Avaliacao Heuristica" in analise_text
        needs_update = is_heuristic or (match_val == 0 and "Filtro Automático" not in analise_text)

        if needs_update:
            title_val = "Vaga"
            if title_k and props.get(title_k, {}).get('title'):
                title_val = ''.join([t.get('plain_text', '') for t in props[title_k]['title']])
                
            empresa_val = ""
            if empresa_k:
                eprop = props.get(empresa_k, {})
                if eprop.get('type') == 'rich_text':
                    empresa_val = ''.join([t.get('plain_text', '') for t in eprop.get('rich_text', [])])
                elif eprop.get('type') == 'select' and eprop.get('select'):
                    empresa_val = eprop['select'].get('name', '')

            print(f"⚙️ A avaliar: {title_val} ({empresa_val})...")
            
            # Avaliação via IA ou Heurística Calibrada
            ai_res = call_gemini(title_val, empresa_val, analise_text)
            if not ai_res or not isinstance(ai_res, dict) or 'score' not in ai_res:
                ai_res = fallback_score(title_val, analise_text)
                
            new_score = float(ai_res.get('score', 70.0))
            raw_just = ai_res.get('justificativa', '')
            raw_just = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]', '', raw_just)
            raw_just = re.sub(r'^(?:Adequada|Inadequada)\s*(?:\([^)]+\))?:\s*', '', raw_just, flags=re.IGNORECASE).strip()
            new_analise = raw_just.strip()
            if new_analise:
                new_analise = new_analise[0].upper() + new_analise[1:]
            
            # Atualiza no Notion APENAS 'Análise IA' e 'Match' (Estado 'Candidatado' NÃO é tocado!)
            update_payload = {
                'properties': {
                    analise_k: {'rich_text': [{'text': {'content': new_analise}}]},
                    match_k: {'number': new_score}
                }
            }
            
            update_req = urllib.request.Request(
                f'https://api.notion.com/v1/pages/{page["id"]}',
                data=json.dumps(update_payload).encode('utf-8'),
                headers=notion_headers,
                method='PATCH'
            )
            with urllib.request.urlopen(update_req):
                pass
                
            print(f"   ✔️ Novo Match: {new_score}%")
            print(f"   ✔️ Nova Análise: {new_analise}\n")
            updated += 1
            time.sleep(0.5)

    if not data.get('has_more'):
        break
    cursor = data.get('next_cursor')

print(f"✨ Concluído! Total de vagas reavaliadas e atualizadas: {updated}")
