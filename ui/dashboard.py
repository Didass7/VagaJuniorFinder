import os
import re
import glob
import hashlib
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from core.config import config, load_config

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

STATUS_CONFIG = {
    "Por Candidatar": {"bg": "rgba(239, 68, 68, 0.12)", "border": "rgba(239, 68, 68, 0.35)", "text": "#FCA5A5", "dot": "#EF4444", "display": "🔴 Por Candidatar"},
    "Candidatado": {"bg": "rgba(16, 185, 129, 0.12)", "border": "rgba(16, 185, 129, 0.35)", "text": "#6EE7B7", "dot": "#10B981", "display": "🟢 Candidatado"},
    "Entrevista": {"bg": "rgba(59, 130, 246, 0.12)", "border": "rgba(59, 130, 246, 0.35)", "text": "#93C5FD", "dot": "#3B82F6", "display": "🔵 Entrevista"},
    "Rejeitado": {"bg": "rgba(100, 116, 139, 0.15)", "border": "rgba(100, 116, 139, 0.35)", "text": "#CBD5E1", "dot": "#94A3B8", "display": "⚪ Rejeitado"},
    "Desqualificada": {"bg": "rgba(245, 158, 11, 0.12)", "border": "rgba(245, 158, 11, 0.35)", "text": "#FCD34D", "dot": "#F59E0B", "display": "🟠 Desqualificada"},
}

STATUS_OPTIONS = ["Por Candidatar", "Candidatado", "Entrevista", "Rejeitado", "Desqualificada"]
STATUS_DISPLAY_OPTIONS = ["🔴 Por Candidatar", "🟢 Candidatado", "🔵 Entrevista", "⚪ Rejeitado", "🟠 Desqualificada"]

def status_to_display(s: str) -> str:
    return STATUS_CONFIG.get(s, {}).get("display", f"⚪ {s}" if s else "🔴 Por Candidatar")

def display_to_status(d: str) -> str:
    if not d:
        return "Por Candidatar"
    for raw, cfg in STATUS_CONFIG.items():
        if raw == d or cfg.get("display") == d:
            return raw
    return d.replace("🔴", "").replace("🟢", "").replace("🔵", "").replace("⚪", "").replace("🟠", "").strip()

def format_date_pt(val: str) -> str:
    """Formats ISO or raw date strings into readable European format (DD/MM/YYYY or DD/MM/YYYY HH:MM)."""
    if not val:
        return ""
    val = str(val).strip()
    try:
        if "T" in val:
            clean_val = val.split(".")[0] if "." in val else val
            clean_val = clean_val.replace("Z", "")
            if "+" in clean_val:
                clean_val = clean_val.split("+")[0]
            dt = datetime.fromisoformat(clean_val)
            if dt.hour == 0 and dt.minute == 0:
                return dt.strftime("%d/%m/%Y")
            return dt.strftime("%d/%m/%Y %H:%M")
        if len(val) == 10 and val.count("-") == 2:
            dt = datetime.strptime(val, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
    except Exception:
        import logging
        logging.warning('Exception swallowed')
    if len(val) >= 10 and val[4] == "-" and val[7] == "-":
        parts = val[:10].split("-")
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return val

COMMON_TECHS = [
    "python", "sql", "langchain", "llamaindex", "fastapi", "flask", "django",
    "pytorch", "tensorflow", "scikit-learn", "sklearn", "pandas", "numpy", "duckdb",
    "docker", "kubernetes", "aws", "gcp", "azure", "snowflake", "spark", "databricks",
    "rag", "llm", "genai", "nlp", "git", "ci/cd", "power bi", "tableau", "react"
]

def extract_tech_chips(text: str) -> list[str]:
    """Finds known tech stack keywords to render as visual pills."""
    found = []
    text_lower = text.lower()
    for tech in COMMON_TECHS:
        if re.search(rf"\b{re.escape(tech)}\b", text_lower):
            found.append(tech.title() if len(tech) > 3 else tech.upper())
    return found[:6]

def get_avatar_gradient(name: str) -> str:
    """Generates deterministic pleasant gradient for company avatars."""
    gradients = [
        "linear-gradient(135deg, #1E293B, #334155)",
        "linear-gradient(135deg, #1E3A8A, #1D4ED8)",
        "linear-gradient(135deg, #064E3B, #047857)",
        "linear-gradient(135deg, #78350F, #B45309)",
        "linear-gradient(135deg, #4C1D95, #6D28D9)",
        "linear-gradient(135deg, #0F766E, #0E7490)"
    ]
    idx = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16) % len(gradients)
    return gradients[idx]

def fetch_jobs_from_notion(token: str, database_id: str) -> list[dict]:
    if not token or not database_id:
        return []
    
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    jobs = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            for page in data.get("results", []):
                page_id = page.get("id")
                props = page.get("properties", {})
                
                title = ""
                company = ""
                score = 0.0
                seniority = ""
                work_mode = ""
                source = ""
                link = ""
                iefp = False
                status = "Por Candidatar"
                ai_reasoning = ""
                date_str = ""

                for p_name, p_data in props.items():
                    p_type = p_data.get("type")
                    name_lower = p_name.lower()

                    if p_type == "title":
                        tl = p_data.get("title", [])
                        if tl:
                            title = tl[0].get("text", {}).get("content", "")
                    elif p_type == "url":
                        link = p_data.get("url") or link
                    elif "empresa" in name_lower or "company" in name_lower:
                        if p_type == "rich_text":
                            rt = p_data.get("rich_text", [])
                            if rt:
                                company = rt[0].get("text", {}).get("content", "")
                        elif p_type == "select" and p_data.get("select"):
                            company = p_data.get("select", {}).get("name", "")
                    elif "score" in name_lower or "match" in name_lower:
                        if p_type == "number":
                            score = float(p_data.get("number") or 0.0)
                    elif "senioridade" in name_lower or "nível" in name_lower or "seniority" in name_lower:
                        if p_type == "select" and p_data.get("select"):
                            seniority = p_data.get("select", {}).get("name", "")
                    elif "modo" in name_lower or "work mode" in name_lower:
                        if p_type == "select" and p_data.get("select"):
                            work_mode = p_data.get("select", {}).get("name", "")
                    elif "fonte" in name_lower or "source" in name_lower:
                        if p_type == "select" and p_data.get("select"):
                            source = p_data.get("select", {}).get("name", "")
                    elif "iefp" in name_lower:
                        if p_type == "checkbox":
                            iefp = p_data.get("checkbox", False)
                    elif "estado" in name_lower or "status" in name_lower:
                        if p_type == "select" and p_data.get("select"):
                            status = p_data.get("select", {}).get("name", "Por Candidatar")
                        elif p_type == "status" and p_data.get("status"):
                            status = p_data.get("status", {}).get("name", "Por Candidatar")
                    elif "análise" in name_lower or "ia" in name_lower or "notas" in name_lower:
                        if p_type == "rich_text":
                            rt = p_data.get("rich_text", [])
                            if rt:
                                ai_reasoning = rt[0].get("text", {}).get("content", "")
                    elif "data" in name_lower or "date" in name_lower:
                        if p_type == "date" and p_data.get("date"):
                            date_str = p_data.get("date", {}).get("start", "")

                if title or link:
                    jobs.append({
                        "page_id": page_id,
                        "title": title or "Sem Título",
                        "company": company or "Empresa Confidencial",
                        "score": score,
                        "seniority": seniority or "Júnior",
                        "work_mode": work_mode or "Presencial / Híbrido",
                        "source": source or "Web",
                        "link": link or "#",
                        "iefp_eligible": iefp,
                        "status": status or "Por Candidatar",
                        "ai_reasoning": ai_reasoning,
                        "date": date_str
                    })

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        except Exception:
            break
            
    return jobs

def update_job_status_in_notion(page_id: str, new_status: str, token: str) -> bool:
    if not page_id or not token:
        return False
    
    url = f"{NOTION_API_URL}/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    payload = {
        "properties": {
            "Estado": {
                "select": {"name": new_status}
            }
        }
    }
    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False

def handle_status_change(page_id: str, profile_name: str, widget_key: str, token: str):
    new_status = st.session_state.get(widget_key)
    if not new_status:
        return
    
    state_key = f"jobs_data_{profile_name}"
    if state_key in st.session_state:
        for j in st.session_state[state_key]:
            if j.get("page_id") == page_id:
                j["status"] = new_status
                break

    ok = update_job_status_in_notion(page_id, new_status, token)
    if ok:
        st.toast(f"Vaga atualizada para '{new_status}' no Notion.")
        st.cache_data.clear()
    else:
        st.toast("Erro ao atualizar o estado no Notion.")

def parse_markdown_reports() -> list[dict]:
    jobs = []
    report_files = sorted(glob.glob(os.path.join("reports", "*.md")), reverse=True)
    
    for rf in report_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                content = f.read()
                
            blocks = re.split(r"\n---\n", content)
            for block in blocks:
                title_match = re.search(r"### \[(.*?)\]\((.*?)\)", block)
                if not title_match:
                    continue
                title, link = title_match.group(1), title_match.group(2)
                
                company_match = re.search(r"\*\*Empresa:\*\*\s*([^\&\|]+)", block)
                company = company_match.group(1).strip() if company_match else "Empresa Confidencial"
                
                source_match = re.search(r"\*\*Fonte:\*\*\s*`([^`]+)`", block)
                source = source_match.group(1).strip() if source_match else "Web"
                
                match_match = re.search(r"\*\*Match:\*\*\s*`([\d\.]+)%?`", block)
                score = float(match_match.group(1)) if match_match else 70.0
                
                work_mode = "Remoto" if "remoto" in block.lower() else "Presencial / Híbrido"
                seniority = "Recém-licenciado" if any(x in block.lower() for x in ["recém", "recem", "estágio", "iefp"]) else "Júnior"
                
                ai_match = re.search(r"(?:🤖\s*)?\*\*Análise IA:\*\*\s*\*?(.*?)\*?\n", block)
                ai_reasoning = ai_match.group(1).strip() if ai_match else ""
                
                jobs.append({
                    "page_id": None,
                    "title": title,
                    "company": company,
                    "score": score,
                    "seniority": seniority,
                    "work_mode": work_mode,
                    "source": source,
                    "link": link,
                    "iefp_eligible": "iefp" in block.lower(),
                    "status": "Por Candidatar",
                    "ai_reasoning": ai_reasoning,
                    "date": os.path.basename(rf).replace("job_report_", "").replace(".md", "")
                })
        except Exception:
            continue
            
    return jobs

@st.cache_data(ttl=180)
def load_all_jobs(profile_name: str) -> list[dict]:
    p_cfg = load_config(profile_name)
    jobs = []
    
    if p_cfg.notion_token and p_cfg.notion_database_id:
        jobs = fetch_jobs_from_notion(p_cfg.notion_token, p_cfg.notion_database_id)
        
    if not jobs:
        jobs = parse_markdown_reports()
        
    return jobs

def render_dashboard(active_profile: str):
    p_cfg = load_config(active_profile)
    state_key = f"jobs_data_{active_profile}"

    # Top Action Bar
    col_t1, col_t2 = st.columns([3.6, 1.4])
    with col_t1:
        st.markdown(
            f"""
            <div style="margin-bottom: 4px;">
                <h1 style="font-size: 24px; font-weight: 800; margin: 0; color: #F8FAFC; letter-spacing: -0.5px;">Feed de Oportunidades</h1>
                <div style="font-size: 13px; color: #94A3B8; margin-top: 2px;">Vagas qualificadas com inteligência artificial para <b style="color: #E2E8F0;">{active_profile}</b></div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_t2:
        st.write("")
        if st.button("Sincronizar Notion", use_container_width=True):
            st.cache_data.clear()
            st.session_state[state_key] = load_all_jobs(active_profile)
            st.rerun()

    if state_key not in st.session_state:
        st.session_state[state_key] = load_all_jobs(active_profile)

    jobs_data = st.session_state[state_key]

    if not jobs_data:
        st.info("Nenhuma vaga encontrada na base de dados. Inicie a pesquisa no separador Executar Pipeline.")
        return

    df = pd.DataFrame(jobs_data)

    # ── Status Counts ──
    count_por_candidatar = len(df[df["status"] == "Por Candidatar"])
    count_candidatado = len(df[df["status"] == "Candidatado"])
    count_entrevista = len(df[df["status"] == "Entrevista"])
    count_rejeitado = len(df[df["status"] == "Rejeitado"])
    total_jobs = len(df)

    # ── Interactive Status KPI Metric Cards ──
    filter_state_key = f"status_filter_{active_profile}"
    if filter_state_key not in st.session_state:
        if count_por_candidatar > 0:
            st.session_state[filter_state_key] = "Por Candidatar"
        elif count_candidatado > 0:
            st.session_state[filter_state_key] = "Candidatado"
        else:
            st.session_state[filter_state_key] = "Todas"

    current_status_filter = st.session_state.get(filter_state_key, "Todas")

    kpi_cards = [
        {"id": "Por Candidatar", "label": "Por Candidatar", "count": count_por_candidatar, "dot": "🔴", "css_key": "por_candidatar"},
        {"id": "Candidatado", "label": "Candidatadas", "count": count_candidatado, "dot": "🟢", "css_key": "candidatado"},
        {"id": "Entrevista", "label": "Em Entrevista", "count": count_entrevista, "dot": "🔵", "css_key": "entrevista"},
        {"id": "Rejeitado", "label": "Rejeitadas", "count": count_rejeitado, "dot": "⚪", "css_key": "rejeitado"},
        {"id": "Todas", "label": "Total no Hub", "count": total_jobs, "dot": "🟣", "css_key": "todas"},
    ]

    cols_kpi = st.columns(5)
    for i, card in enumerate(kpi_cards):
        is_selected = (current_status_filter == card["id"])
        with cols_kpi[i]:
            btn_title = f"{card['dot']} {card['label']}  \n\n{card['count']}"
            if st.button(
                btn_title,
                key=f"kpicard_{card['css_key']}_{active_profile}",
                use_container_width=True,
                type="primary" if is_selected else "secondary"
            ):
                st.session_state[filter_state_key] = card["id"]
                st.rerun()

    status_filter = current_status_filter

    # ── Search & View Controls (Clean & Focused) ──
    with st.container(border=True):
        col_s1, col_s2 = st.columns([3.6, 1.4], vertical_alignment="center")
        with col_s1:
            search_query = st.text_input(
                "Pesquisa Instantânea",
                value=st.session_state.get(f"search_query_{active_profile}", ""),
                placeholder="🔍 Pesquisar por cargo, empresa, tecnologia ou localidade (ex: Python, LangChain, Lisboa)...",
                label_visibility="collapsed",
                key=f"search_query_{active_profile}"
            ).strip().lower()
        with col_s2:
            view_mode = st.segmented_control(
                "Visualização",
                options=["Tabela", "Cards Visuais"],
                default="Tabela",
                format_func=lambda x: "☰ Tabela" if x == "Tabela" else "⊞ Cards Visuais",
                selection_mode="single",
                required=True,
                label_visibility="collapsed",
                key=f"view_mode_{active_profile}",
                width="stretch"
            )
            if not view_mode:
                view_mode = "Tabela"

    # Apply all filters
    filtered_df = df.copy()

    # 1. Status Filter from Top Tabs
    if status_filter != "Todas":
        filtered_df = filtered_df[filtered_df["status"] == status_filter]

    # 2. Search Query (Multi-keyword token matching)
    if search_query:
        for word in search_query.split():
            filtered_df = filtered_df[
                filtered_df["title"].str.lower().str.contains(word, na=False) |
                filtered_df["company"].str.lower().str.contains(word, na=False) |
                filtered_df["ai_reasoning"].str.lower().str.contains(word, na=False) |
                filtered_df["source"].str.lower().str.contains(word, na=False) |
                filtered_df["work_mode"].str.lower().str.contains(word, na=False) |
                filtered_df["seniority"].str.lower().str.contains(word, na=False)
            ]

    filtered_df = filtered_df.sort_values(by="score", ascending=False).reset_index(drop=True)

    filter_badge = " <span style='background: rgba(59, 130, 246, 0.15); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.3); padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;'>Pesquisa Ativa</span>" if bool(search_query) else ""

    st.markdown(f"<div style='font-size: 12.5px; font-weight: 600; color: #94A3B8; margin: 12px 0 8px 0;'>A mostrar <b style='color: #F8FAFC;'>{len(filtered_df)}</b> de <b style='color: #F8FAFC;'>{total_jobs}</b> vagas{filter_badge}</div>", unsafe_allow_html=True)

    if filtered_df.empty:
        st.info("Nenhuma vaga encontrada com os filtros selecionados.")
        return

    # ── Render Views ──
    if "Tabela" in str(view_mode):
        table_df = filtered_df.copy()
        table_df["status_display"] = table_df["status"].apply(status_to_display)
        table_df["date"] = table_df["date"].apply(format_date_pt)

        display_cols = ["status_display", "title", "company", "score", "work_mode", "source", "link", "date"]
        editor_key = f"table_editor_{active_profile}"

        edited_df = st.data_editor(
            table_df[display_cols],
            column_config={
                "status_display": st.column_config.SelectboxColumn(
                    "Estado",
                    help="Clique para alterar o estado da vaga diretamente",
                    width="medium",
                    options=STATUS_DISPLAY_OPTIONS,
                    required=True
                ),
                "title": st.column_config.TextColumn("Cargo", disabled=True),
                "company": st.column_config.TextColumn("Empresa", disabled=True),
                "score": st.column_config.ProgressColumn("Match Score", format="%.1f%%", min_value=0, max_value=100),
                "work_mode": st.column_config.TextColumn("Modalidade", disabled=True),
                "source": st.column_config.TextColumn("Fonte", disabled=True),
                "link": st.column_config.LinkColumn("Link de Candidatura", display_text="Ver Vaga ↗", disabled=True),
                "date": st.column_config.TextColumn("Data Extração", disabled=True)
            },
            disabled=["title", "company", "score", "work_mode", "source", "link", "date"],
            use_container_width=True,
            hide_index=True,
            height=min(max(len(table_df) * 38 + 45, 500), 850),
            key=editor_key
        )

        # Detect in-table status modifications
        if editor_key in st.session_state and "edited_rows" in st.session_state[editor_key]:
            edited_rows = st.session_state[editor_key]["edited_rows"]
            has_changes = False
            for row_idx_str, changes in edited_rows.items():
                if "status_display" in changes:
                    try:
                        row_idx = int(row_idx_str)
                        if 0 <= row_idx < len(filtered_df):
                            new_status_disp = changes["status_display"]
                            new_status_raw = display_to_status(new_status_disp)
                            page_id = filtered_df.iloc[row_idx].get("page_id")
                            job_title = filtered_df.iloc[row_idx].get("title", "Vaga")

                            # Update session cache
                            state_key_act = f"jobs_data_{active_profile}"
                            if state_key_act in st.session_state and page_id:
                                for j in st.session_state[state_key_act]:
                                    if j.get("page_id") == page_id:
                                        j["status"] = new_status_raw
                                        break

                            # Sync to Notion
                            if page_id and p_cfg.notion_token:
                                ok = update_job_status_in_notion(page_id, new_status_raw, p_cfg.notion_token)
                                if ok:
                                    st.toast(f"Estado de '{job_title[:25]}' atualizado para '{new_status_disp}' no Notion!")
                                else:
                                    st.toast("Erro ao atualizar o estado no Notion.")
                            has_changes = True
                    except Exception:
                        import logging
                        logging.warning('Exception swallowed')
            if has_changes:
                st.cache_data.clear()
                st.rerun()
    else:
        # Visual Cards View (Compact High-Density Design)
        for idx, row in filtered_df.iterrows():
            score_val = row['score']
            if score_val >= 75:
                score_gradient = "linear-gradient(135deg, #059669, #10B981)"
                score_label = "TOP"
            elif score_val >= 60:
                score_gradient = "linear-gradient(135deg, #2563EB, #3B82F6)"
                score_label = "BOM"
            else:
                score_gradient = "linear-gradient(135deg, #475569, #64748B)"
                score_label = "OK"

            company_initial = row['company'][:2].upper() if row['company'] else "EM"
            avatar_bg = get_avatar_gradient(row['company'])

            tech_chips = extract_tech_chips(f"{row['title']} {row.get('ai_reasoning', '')}")
            tech_html = "".join([f'<span style="background: #1E293B; color: #93C5FD; border: 1px solid rgba(255, 255, 255, 0.08); padding: 1px 5px; border-radius: 4px; font-size: 10px; font-weight: 600;">{t}</span> ' for t in tech_chips])
            iefp_badge_html = '<span style="background: rgba(16, 185, 129, 0.12); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.25); padding: 1px 5px; border-radius: 4px; font-size: 10px; font-weight: 700;">IEFP</span> ' if row.get("iefp_eligible") else ''

            with st.container(border=True):
                # Row 1: Core Info + Score + Status Dropdown + Action Link
                c_avatar, c_info, c_score, c_status, c_link = st.columns([0.35, 3.0, 0.85, 1.2, 0.7], vertical_alignment="center")

                with c_avatar:
                    st.markdown(
                        f"""
                        <div style="width: 32px; height: 32px; border-radius: 6px; background: {avatar_bg}; border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; font-weight: 700; color: #F1F5F9; font-size: 11.5px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
                            {company_initial}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with c_info:
                    st.markdown(
                        f"""
                        <div style="line-height: 1.3; overflow: hidden; padding-right: 6px;">
                            <a href="{row['link']}" target="_blank" style="text-decoration: none; color: #F8FAFC; font-weight: 700; font-size: 13.5px; letter-spacing: -0.2px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; display: block;">
                                {row['title']} <span style="font-size: 11px; color: #64748B; font-weight: normal;">↗</span>
                            </a>
                            <div style="color: #94A3B8; font-size: 11px; margin-top: 1px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">
                                <b style="color: #E2E8F0;">{row['company']}</b> &nbsp;•&nbsp; {row['work_mode']} &nbsp;•&nbsp; {row['source']} &nbsp;•&nbsp; {row['seniority']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with c_score:
                    st.markdown(
                        f"""
                        <div style="background: {score_gradient}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: 800; font-size: 10.5px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.25); white-space: nowrap;">
                            {score_val:.1f}% <span style="font-size: 8px; font-weight: 600; opacity: 0.9;">{score_label}</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with c_status:
                    st_cfg = STATUS_CONFIG.get(row['status'], {"bg": "rgba(55, 65, 81, 0.2)", "border": "rgba(255, 255, 255, 0.1)", "text": "#E5E7EB", "dot": "#94A3B8"})
                    if row.get("page_id") and p_cfg.notion_token:
                        widget_key = f"status_sel_{row['page_id']}"
                        st.selectbox(
                            "Estado",
                            options=STATUS_OPTIONS,
                            format_func=lambda x: STATUS_CONFIG.get(x, {}).get("display", x),
                            index=STATUS_OPTIONS.index(row["status"]) if row["status"] in STATUS_OPTIONS else 0,
                            key=widget_key,
                            on_change=handle_status_change,
                            args=(row["page_id"], active_profile, widget_key, p_cfg.notion_token),
                            label_visibility="collapsed"
                        )
                    else:
                        bg_c = st_cfg.get("bg", "rgba(55, 65, 81, 0.2)")
                        br_c = st_cfg.get("border", "rgba(255, 255, 255, 0.1)")
                        tx_c = st_cfg.get("text", "#E5E7EB")
                        disp_st = status_to_display(row['status'])
                        st.markdown(
                            f'<div style="background: {bg_c}; border: 1px solid {br_c}; color: {tx_c}; padding: 4px 8px; border-radius: 5px; font-size: 11px; font-weight: 600; text-align: center;">{disp_st}</div>',
                            unsafe_allow_html=True
                        )
                with c_link:
                    st.link_button("Ver ↗", row["link"], use_container_width=True)

                # Row 2: Subtle AI note & Tech chips in one compact line
                if row.get("ai_reasoning") or tech_html or iefp_badge_html:
                    ai_text = f"<span style='color: #A5B4FC; font-weight: 600;'>Avaliação:</span> <i>{row['ai_reasoning']}</i>" if row.get("ai_reasoning") else ""
                    chips_html = f"<div style='display: flex; gap: 4px; flex-shrink: 0; align-items: center;'>{iefp_badge_html}{tech_html}</div>" if (iefp_badge_html or tech_html) else ""
                    st.markdown(
                        f"<div style='display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 4px; padding-top: 4px; border-top: 1px solid rgba(255, 255, 255, 0.05); font-size: 11px; color: #94A3B8;'><div style='overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;'>{ai_text}</div>{chips_html}</div>",
                        unsafe_allow_html=True
                    )

