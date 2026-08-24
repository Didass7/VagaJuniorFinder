import os
import re
import glob
import pandas as pd
import requests
import streamlit as st
from config import config, load_config

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

STATUS_COLORS = {
    "Por Candidatar": {"bg": "#9A3412", "text": "#FFFFFF", "icon": "🔴"},
    "Candidatado": {"bg": "#15803D", "text": "#FFFFFF", "icon": "🟢"},
    "Entrevista": {"bg": "#1D4ED8", "text": "#FFFFFF", "icon": "🔵"},
    "Rejeitado": {"bg": "#4B5563", "text": "#FFFFFF", "icon": "⚪"},
    "Desqualificada": {"bg": "#B45309", "text": "#FFFFFF", "icon": "🟡"},
}

STATUS_OPTIONS = ["Por Candidatar", "Candidatado", "Entrevista", "Rejeitado", "Desqualificada"]

def fetch_jobs_from_notion(token: str, database_id: str) -> list[dict]:
    """Queries Notion database and returns structured list of jobs."""
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
    """Updates the 'Estado' property of a job page directly in Notion."""
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

def parse_markdown_reports() -> list[dict]:
    """Fallback reader: parses existing reports/job_report_*.md if Notion is offline."""
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
    st.header("🎯 Central de Vagas & Candidaturas")
    
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown(f"Gere e acompanha as oportunidades e candidaturas do candidato: **`{active_profile}`**")
    with col_t2:
        if st.button("🔄 Atualizar Notion / Vagas", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    jobs_data = load_all_jobs(active_profile)

    if not jobs_data:
        st.info("ℹ️ Nenhuma vaga encontrada na base de dados. Experimenta executar a pesquisa na aba **🚀 Executar Pesquisa**!")
        return

    df = pd.DataFrame(jobs_data)

    # ── Status Counts ──
    count_por_candidatar = len(df[df["status"] == "Por Candidatar"])
    count_candidatado = len(df[df["status"] == "Candidatado"])
    count_entrevista = len(df[df["status"] == "Entrevista"])
    count_rejeitado = len(df[df["status"] == "Rejeitado"])
    count_desqualificada = len(df[df["status"] == "Desqualificada"])
    total_jobs = len(df)

    # ── KPIs Top Bar ──
    st.divider()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🔴 Por Candidatar", f"{count_por_candidatar}")
    k2.metric("🟢 Candidatadas", f"{count_candidatado}")
    k3.metric("🔵 Em Entrevista", f"{count_entrevista}")
    k4.metric("⚪ Rejeitadas", f"{count_rejeitado}")
    k5.metric("📁 Total de Vagas", f"{total_jobs}")

    st.divider()

    # ── Primary Division: Status Navigation (Tabs / Radio) ──
    status_nav_options = [
        f"🔴 Por Candidatar ({count_por_candidatar})",
        f"🟢 Candidatado ({count_candidatado})",
        f"🔵 Entrevista ({count_entrevista})",
        f"⚪ Rejeitado ({count_rejeitado})",
        f"📁 Todas as Vagas ({total_jobs})"
    ]

    selected_status_tab = st.radio(
        "📌 Divisão por Estado de Candidatura:",
        options=status_nav_options,
        index=0,
        horizontal=True,
        key="status_radio_selector"
    )

    # Map selected tab back to status filter
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

    # ── Secondary Interactive Filter Controls ──
    with st.expander("🔍 Filtros Adicionais (Score, Portal, Modalidade)", expanded=False):
        f1, f2, f3 = st.columns(3)
        with f1:
            search_query = st.text_input("Filtrar por Cargo, Empresa ou Tecnologia:", placeholder="ex: Python, LangChain, Lisboa...").strip().lower()
            min_score = st.slider("Match Score Mínimo (%):", min_value=0, max_value=100, value=50, step=5)
        with f2:
            sources = ["Todas"] + sorted(list(set(df["source"].dropna().unique())))
            selected_source = st.selectbox("Portal de Origem:", options=sources)
            modes = ["Todas"] + sorted(list(set(df["work_mode"].dropna().unique())))
            selected_mode = st.selectbox("Modalidade de Trabalho:", options=modes)
        with f3:
            seniorities = ["Todas"] + sorted(list(set(df["seniority"].dropna().unique())))
            selected_seniority = st.selectbox("Nível de Senioridade:", options=seniorities)
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

    # Sort descending by score
    filtered_df = filtered_df.sort_values(by="score", ascending=False)

    st.subheader(f"📋 {selected_status_tab} — {len(filtered_df)} vagas listadas")

    if filtered_df.empty:
        st.info(f"Nenhuma vaga encontrada com os filtros selecionados para o estado '{status_filter}'.")
        return

    # View Mode Toggle
    view_mode = st.radio("Formato de Visualização:", ["Cards Visuais", "Tabela Interativa"], horizontal=True, key="view_mode_radio")

    if view_mode == "Tabela Interativa":
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
                "date": "Data Ingestão"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        for idx, row in filtered_df.iterrows():
            score_val = row['score']
            if score_val >= 75:
                badge_color = "#10B981"
                score_label = "🔥 Top Match"
            elif score_val >= 60:
                badge_color = "#3B82F6"
                score_label = "⭐ Promissora"
            else:
                badge_color = "#6B7280"
                score_label = "Aceitável"

            st_info = STATUS_COLORS.get(row['status'], {"bg": "#374151", "text": "#FFFFFF", "icon": "🏷️"})

            with st.container(border=True):
                c_title, c_badges = st.columns([3, 1])
                with c_title:
                    st.markdown(f"### [{row['title']}]({row['link']})")
                    st.markdown(f"🏢 **{row['company']}** &nbsp;|&nbsp; 📍 **{row['work_mode']}** &nbsp;|&nbsp; 🌐 **{row['source']}** &nbsp;|&nbsp; 🎓 **{row['seniority']}**")
                
                with c_badges:
                    st.markdown(
                        f"""
                        <div style="display: flex; gap: 8px; justify-content: flex-end; align-items: center;">
                            <div style="background-color: {st_info['bg']}; color: {st_info['text']}; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 13px;">
                                {st_info['icon']} {row['status']}
                            </div>
                            <div style="background-color: {badge_color}; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 13px;">
                                {score_val:.1f}%
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                if row.get("ai_reasoning"):
                    st.markdown(f"🤖 **Análise da IA:** *{row['ai_reasoning']}*")

                col_a1, col_a2, col_a3 = st.columns([2, 1.5, 1.5])
                with col_a1:
                    if row.get("iefp_eligible"):
                        st.caption("✅ Elegível para Estágio Profissional IEFP / ATIVAR.pt")
                
                with col_a2:
                    # Status Quick Action
                    if row.get("page_id") and p_cfg.notion_token:
                        current_st = row["status"]
                        new_st = st.selectbox(
                            "Alterar Estado (Notion):",
                            options=STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(current_st) if current_st in STATUS_OPTIONS else 0,
                            key=f"status_select_{row['page_id']}_{idx}",
                            label_visibility="collapsed"
                        )
                        if new_st != current_st:
                            if update_job_status_in_notion(row["page_id"], new_st, p_cfg.notion_token):
                                st.toast(f"✅ Estado atualizado para '{new_st}' no Notion!")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar estado no Notion.")

                with col_a3:
                    st.link_button("👉 Abrir Vaga", row["link"], use_container_width=True)
