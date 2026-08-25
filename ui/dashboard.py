import os
import re
import glob
import hashlib
import pandas as pd
import requests
import streamlit as st
from config import config, load_config

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

STATUS_CONFIG = {
    "Por Candidatar": {"bg": "rgba(239, 68, 68, 0.15)", "border": "rgba(239, 68, 68, 0.4)", "text": "#FCA5A5", "icon": "🔴", "label": "🔴 Por Candidatar"},
    "Candidatado": {"bg": "rgba(16, 185, 129, 0.15)", "border": "rgba(16, 185, 129, 0.4)", "text": "#6EE7B7", "icon": "🟢", "label": "🟢 Candidatado"},
    "Entrevista": {"bg": "rgba(59, 130, 246, 0.15)", "border": "rgba(59, 130, 246, 0.4)", "text": "#93C5FD", "icon": "🔵", "label": "🔵 Entrevista"},
    "Rejeitado": {"bg": "rgba(100, 116, 139, 0.15)", "border": "rgba(100, 116, 139, 0.4)", "text": "#CBD5E1", "icon": "⚪", "label": "⚪ Rejeitado"},
    "Desqualificada": {"bg": "rgba(245, 158, 11, 0.15)", "border": "rgba(245, 158, 11, 0.4)", "text": "#FCD34D", "icon": "🟡", "label": "🟡 Desqualificada"},
}

STATUS_OPTIONS = ["Por Candidatar", "Candidatado", "Entrevista", "Rejeitado", "Desqualificada"]

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
        "linear-gradient(135deg, #2563EB, #7C3AED)",
        "linear-gradient(135deg, #059669, #10B981)",
        "linear-gradient(135deg, #D97706, #F59E0B)",
        "linear-gradient(135deg, #DC2626, #EF4444)",
        "linear-gradient(135deg, #7C3AED, #EC4899)",
        "linear-gradient(135deg, #0284C7, #06B6D4)"
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
        st.toast(f"✅ Vaga atualizada para '{new_status}' no Notion!")
        st.cache_data.clear()
    else:
        st.toast("⚠️ Erro ao atualizar no Notion.", icon="❌")

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
                
                ai_match = re.search(r"🤖 \*\*Análise IA:\*\*\s*\*?(.*?)\*?\n", block)
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
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown(
            f"""
            <div style="margin-bottom: 4px;">
                <h1 style="font-size: 26px; font-weight: 800; margin: 0; color: #F8FAFC; letter-spacing: -0.5px;">🎯 Feed de Vagas & Oportunidades</h1>
                <div style="font-size: 13px; color: #94A3B8;">Oportunidades qualificadas com inteligência artificial para <b>{active_profile}</b></div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_t2:
        if st.button("⚡ Sincronizar Notion", use_container_width=True):
            st.cache_data.clear()
            st.session_state[state_key] = load_all_jobs(active_profile)
            st.rerun()

    if state_key not in st.session_state:
        st.session_state[state_key] = load_all_jobs(active_profile)

    jobs_data = st.session_state[state_key]

    if not jobs_data:
        st.info("ℹ️ Nenhuma vaga encontrada na base de dados. Experimenta executar a pesquisa na aba **🚀 Executar Pesquisa**!")
        return

    df = pd.DataFrame(jobs_data)

    # ── Status Counts ──
    count_por_candidatar = len(df[df["status"] == "Por Candidatar"])
    count_candidatado = len(df[df["status"] == "Candidatado"])
    count_entrevista = len(df[df["status"] == "Entrevista"])
    count_rejeitado = len(df[df["status"] == "Rejeitado"])
    total_jobs = len(df)

    # ── Modern KPI Cards Bar ──
    st.write("")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🔴 Por Candidatar", f"{count_por_candidatar}")
    k2.metric("🟢 Candidatadas", f"{count_candidatado}")
    k3.metric("🔵 Em Entrevista", f"{count_entrevista}")
    k4.metric("⚪ Rejeitadas", f"{count_rejeitado}")
    k5.metric("📁 Total no Hub", f"{total_jobs}")

    st.divider()

    # ── Primary Division: Status Navigation Pills ──
    status_nav_options = [
        f"🔴 Por Candidatar ({count_por_candidatar})",
        f"🟢 Candidatado ({count_candidatado})",
        f"🔵 Entrevista ({count_entrevista})",
        f"⚪ Rejeitado ({count_rejeitado})",
        f"📁 Todas as Vagas ({total_jobs})"
    ]

    if count_por_candidatar > 0:
        default_tab_idx = 0
    elif count_candidatado > 0:
        default_tab_idx = 1
    elif count_entrevista > 0:
        default_tab_idx = 2
    else:
        default_tab_idx = 4

    selected_status_tab = st.radio(
        "Divisão por Estado de Candidatura:",
        options=status_nav_options,
        index=default_tab_idx,
        horizontal=True,
        key="status_radio_selector",
        label_visibility="collapsed"
    )

    if selected_status_tab and "Por Candidatar" in selected_status_tab:
        status_filter = "Por Candidatar"
    elif selected_status_tab and "Candidatado" in selected_status_tab:
        status_filter = "Candidatado"
    elif selected_status_tab and "Entrevista" in selected_status_tab:
        status_filter = "Entrevista"
    elif selected_status_tab and "Rejeitado" in selected_status_tab:
        status_filter = "Rejeitado"
    else:
        status_filter = "Todas"

    # ── Search & Filter Controls ──
    with st.container(border=True):
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            search_query = st.text_input(
                "Pesquisa Instantânea:",
                placeholder="🔍 Pesquisar por cargo, empresa ou tecnologia (ex: Python, LangChain, Lisboa...)",
                label_visibility="collapsed"
            ).strip().lower()
        with col_s2:
            view_mode = st.radio("Visualização:", ["Cards Visuais", "Tabela"], horizontal=True, label_visibility="collapsed")

        with st.expander("Filtros Avançados (Score, Portal, Modalidade, IEFP)", expanded=False):
            f1, f2, f3 = st.columns(3)
            with f1:
                min_score = st.slider("Match Score Mínimo (%):", min_value=0, max_value=100, value=50, step=5)
            with f2:
                sources = ["Todas"] + sorted(list(set(df["source"].dropna().unique())))
                selected_source = st.selectbox("Portal de Origem:", options=sources)
                modes = ["Todas"] + sorted(list(set(df["work_mode"].dropna().unique())))
                selected_mode = st.selectbox("Modalidade:", options=modes)
            with f3:
                seniorities = ["Todas"] + sorted(list(set(df["seniority"].dropna().unique())))
                selected_seniority = st.selectbox("Senioridade:", options=seniorities)
                only_iefp = st.checkbox("Apenas vagas elegíveis IEFP / ATIVAR.pt", value=False)

    # Apply all filters
    filtered_df = df.copy()

    if status_filter != "Todas":
        filtered_df = filtered_df[filtered_df["status"] == status_filter]

    if search_query:
        filtered_df = filtered_df[
            filtered_df["title"].str.lower().str.contains(search_query, na=False) |
            filtered_df["company"].str.lower().str.contains(search_query, na=False) |
            filtered_df["ai_reasoning"].str.lower().str.contains(search_query, na=False)
        ]
    if min_score > 0:
        filtered_df = filtered_df[filtered_df["score"] >= min_score]
    if selected_source != "Todas":
        filtered_df = filtered_df[filtered_df["source"] == selected_source]
    if selected_mode != "Todas":
        filtered_df = filtered_df[filtered_df["work_mode"] == selected_mode]
    if selected_seniority != "Todas":
        filtered_df = filtered_df[filtered_df["seniority"] == selected_seniority]
    if only_iefp:
        filtered_df = filtered_df[filtered_df["iefp_eligible"] == True]

    filtered_df = filtered_df.sort_values(by="score", ascending=False).reset_index(drop=True)

    st.markdown(f"<div style='font-size: 13px; font-weight: 600; color: #94A3B8; margin: 12px 0 8px 0;'>A mostrar {len(filtered_df)} de {total_jobs} vagas</div>", unsafe_allow_html=True)

    if filtered_df.empty:
        st.info(f"Nenhuma vaga encontrada com os filtros selecionados.")
        return

    # ── Render Views ──
    if view_mode == "Tabela":
        st.dataframe(
            filtered_df[["status", "title", "company", "score", "seniority", "work_mode", "source", "link", "date"]],
            column_config={
                "status": "Estado",
                "title": "Cargo",
                "company": "Empresa",
                "score": st.column_config.ProgressColumn("Match Score", format="%.1f%%", min_value=0, max_value=100),
                "seniority": "Senioridade",
                "work_mode": "Modalidade",
                "source": "Fonte",
                "link": st.column_config.LinkColumn("Link de Candidatura"),
                "date": "Data Extração"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        # Visual Cards View
        for idx, row in filtered_df.iterrows():
            score_val = row['score']
            if score_val >= 75:
                score_gradient = "linear-gradient(135deg, #10B981, #059669)"
                score_label = "🔥 TOP MATCH"
            elif score_val >= 60:
                score_gradient = "linear-gradient(135deg, #3B82F6, #1D4ED8)"
                score_label = "⭐ PROMISSORA"
            else:
                score_gradient = "linear-gradient(135deg, #64748B, #475569)"
                score_label = "ADEQUADA"

            st_cfg = STATUS_CONFIG.get(row['status'], {"bg": "rgba(55, 65, 81, 0.2)", "border": "rgba(255, 255, 255, 0.1)", "text": "#E5E7EB", "icon": "🏷️"})
            company_initial = row['company'][:2].upper() if row['company'] else "EM"
            avatar_bg = get_avatar_gradient(row['company'])

            tech_chips = extract_tech_chips(f"{row['title']} {row.get('ai_reasoning', '')}")
            tech_html = "".join([f'<span style="background: rgba(30, 41, 59, 0.8); color: #93C5FD; border: 1px solid rgba(59, 130, 246, 0.2); padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;">{t}</span> ' for t in tech_chips])

            with st.container(border=True):
                # Header Row
                c_avatar, c_content, c_badge = st.columns([0.5, 3.5, 1])
                with c_avatar:
                    st.markdown(
                        f"""
                        <div style="width: 44px; height: 44px; border-radius: 10px; background: {avatar_bg}; display: flex; align-items: center; justify-content: center; font-weight: 800; color: white; font-size: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                            {company_initial}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with c_content:
                    st.markdown(
                        f"""
                        <div style="margin-left: -10px;">
                            <a href="{row['link']}" target="_blank" style="text-decoration: none; color: #F8FAFC; font-weight: 700; font-size: 17px; letter-spacing: -0.2px;">
                                {row['title']} ↗
                            </a>
                            <div style="color: #94A3B8; font-size: 13px; margin-top: 2px;">
                                🏢 <b style="color: #E2E8F0;">{row['company']}</b> &nbsp;•&nbsp; 📍 {row['work_mode']} &nbsp;•&nbsp; 🌐 {row['source']} &nbsp;•&nbsp; 🎓 {row['seniority']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with c_badge:
                    st.markdown(
                        f"""
                        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
                            <div style="background: {score_gradient}; color: white; padding: 4px 10px; border-radius: 8px; font-weight: 800; font-size: 13px; box-shadow: 0 2px 8px rgba(0,0,0,0.25);">
                                {score_val:.1f}% &nbsp;<span style="font-size: 9px; font-weight: 600; opacity: 0.9;">{score_label}</span>
                            </div>
                            <div style="background: {st_cfg['bg']}; border: 1px solid {st_cfg['border']}; color: {st_cfg['text']}; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;">
                                {st_cfg['icon']} {row['status']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # AI Analysis Callout
                if row.get("ai_reasoning"):
                    st.markdown(
                        f"""
                        <div style="background: rgba(30, 41, 59, 0.4); border-left: 3px solid #8B5CF6; border-radius: 6px; padding: 8px 12px; margin: 10px 0 8px 0; font-size: 13px; color: #CBD5E1;">
                            🤖 <b>Análise IA:</b> <i>{row['ai_reasoning']}</i>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # Tech Chips & Action Buttons
                c_chips, c_quick_btn, c_sel, c_open = st.columns([2.5, 1.2, 1.3, 1])
                with c_chips:
                    if tech_html:
                        st.markdown(f"<div style='display: flex; gap: 6px; flex-wrap: wrap; align-items: center; padding-top: 4px;'>{tech_html}</div>", unsafe_allow_html=True)
                    if row.get("iefp_eligible"):
                        st.markdown('<span style="background: rgba(16, 185, 129, 0.1); color: #34D399; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600;">✅ IEFP ATIVAR.PT</span>', unsafe_allow_html=True)

                with c_quick_btn:
                    if row["status"] == "Por Candidatar" and row.get("page_id") and p_cfg.notion_token:
                        if st.button("✅ Candidatar", key=f"quick_apply_{row['page_id']}_{idx}", use_container_width=True):
                            state_key_act = f"jobs_data_{active_profile}"
                            for j in st.session_state.get(state_key_act, []):
                                if j.get("page_id") == row["page_id"]:
                                    j["status"] = "Candidatado"
                                    break
                            update_job_status_in_notion(row["page_id"], "Candidatado", p_cfg.notion_token)
                            st.toast("✅ Marcada como Candidatada no Notion!")
                            st.cache_data.clear()
                            st.rerun()

                with c_sel:
                    if row.get("page_id") and p_cfg.notion_token:
                        widget_key = f"status_sel_{row['page_id']}"
                        st.selectbox(
                            "Estado:",
                            options=STATUS_OPTIONS,
                            format_func=lambda x: STATUS_CONFIG.get(x, {}).get("label", x),
                            index=STATUS_OPTIONS.index(row["status"]) if row["status"] in STATUS_OPTIONS else 0,
                            key=widget_key,
                            on_change=handle_status_change,
                            args=(row["page_id"], active_profile, widget_key, p_cfg.notion_token),
                            label_visibility="collapsed"
                        )

                with c_open:
                    st.link_button("👉 Abrir", row["link"], use_container_width=True)
