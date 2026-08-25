import os
import re
from collections import Counter
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from ui.dashboard import load_all_jobs, STATUS_CONFIG

TECH_KEYWORDS = [
    "python", "sql", "mysql", "postgresql", "duckdb", "pandas", "numpy",
    "scikit-learn", "sklearn", "xgboost", "pytorch", "tensorflow", "keras",
    "fastapi", "flask", "django", "langchain", "llamaindex", "chromadb",
    "rag", "llm", "genai", "nlp", "computer vision", "opencv",
    "docker", "kubernetes", "git", "github actions", "ci/cd",
    "aws", "gcp", "azure", "snowflake", "databricks", "spark", "kafka",
    "power bi", "tableau", "excel", "javascript", "typescript", "react"
]

def extract_tech_frequency(jobs: list[dict]) -> Counter:
    counter = Counter()
    for job in jobs:
        text = f"{job.get('title', '')} {job.get('ai_reasoning', '')}".lower()
        for tech in TECH_KEYWORDS:
            if re.search(rf"\b{re.escape(tech)}\b", text):
                counter[tech.title()] += 1
    return counter

def apply_dark_theme(fig, height=350):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, sans-serif", color="#CBD5E1", size=12),
        margin=dict(l=20, r=20, t=30, b=20),
        height=height,
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.06)"),
    )
    return fig

def render_analytics(active_profile: str):
    st.markdown(
        f"""
        <div style="margin-bottom: 8px;">
            <h1 style="font-size: 26px; font-weight: 800; margin: 0; color: #F8FAFC; letter-spacing: -0.5px;">📊 Métricas & Inteligência de Mercado</h1>
            <div style="font-size: 13px; color: #94A3B8;">Análise estatística e tendências das oportunidades qualificadas para <b>{active_profile}</b>.</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.divider()

    jobs = load_all_jobs(active_profile)
    if not jobs:
        st.info("Ainda não existem vagas registadas para analisar. Executa a pesquisa primeiro!")
        return

    df = pd.DataFrame(jobs)

    # ── Section 1: Candidacy Status Funnel ──
    with st.container(border=True):
        st.markdown("<div style='font-size: 16px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;'>🎯 Funil de Candidaturas (Progresso no Notion)</div>", unsafe_allow_html=True)
        if "status" in df.columns:
            st_counts = df["status"].value_counts().reset_index()
            st_counts.columns = ["Estado", "Total"]

            color_map = {
                "Por Candidatar": "#EF4444",
                "Candidatado": "#10B981",
                "Entrevista": "#3B82F6",
                "Rejeitado": "#64748B",
                "Desqualificada": "#F59E0B"
            }

            fig_status = px.bar(
                st_counts,
                x="Estado",
                y="Total",
                color="Estado",
                text="Total",
                color_discrete_map=color_map
            )
            fig_status = apply_dark_theme(fig_status, height=280)
            fig_status.update_layout(showlegend=False, xaxis_title="", yaxis_title="Total de Vagas")
            st.plotly_chart(fig_status, use_container_width=True)

    st.write("")

    col1, col2 = st.columns(2)

    # 1. Tech Stack Frequency Bar Chart
    with col1:
        with st.container(border=True):
            st.markdown("<div style='font-size: 16px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;'>⚡ Tecnologias Mais Requisitadas</div>", unsafe_allow_html=True)
            tech_counts = extract_tech_frequency(jobs)
            if tech_counts:
                top_techs = tech_counts.most_common(10)
                tech_df = pd.DataFrame(top_techs, columns=["Tecnologia", "Menções"]).sort_values(by="Menções", ascending=True)
                
                fig_tech = px.bar(
                    tech_df,
                    x="Menções",
                    y="Tecnologia",
                    orientation="h",
                    color="Menções",
                    color_continuous_scale="Blues",
                    text="Menções"
                )
                fig_tech = apply_dark_theme(fig_tech, height=340)
                fig_tech.update_layout(showlegend=False, xaxis_title="Número de Vagas", yaxis_title="")
                st.plotly_chart(fig_tech, use_container_width=True)
            else:
                st.caption("Sem dados de tecnologias disponíveis.")

    # 2. Work Mode Distribution Donut Chart
    with col2:
        with st.container(border=True):
            st.markdown("<div style='font-size: 16px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;'>📍 Modalidade de Trabalho</div>", unsafe_allow_html=True)
            if "work_mode" in df.columns:
                mode_counts = df["work_mode"].value_counts().reset_index()
                mode_counts.columns = ["Modalidade", "Quantidade"]
                
                fig_mode = px.pie(
                    mode_counts,
                    values="Quantidade",
                    names="Modalidade",
                    hole=0.5,
                    color_discrete_sequence=["#3B82F6", "#10B981", "#8B5CF6", "#F59E0B"]
                )
                fig_mode = apply_dark_theme(fig_mode, height=340)
                st.plotly_chart(fig_mode, use_container_width=True)
            else:
                st.caption("Sem dados de modalidades disponíveis.")

    st.write("")

    col3, col4 = st.columns(2)

    # 3. Source Portals Distribution
    with col3:
        with st.container(border=True):
            st.markdown("<div style='font-size: 16px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;'>🌐 Vagas por Portal de Origem</div>", unsafe_allow_html=True)
            if "source" in df.columns:
                source_counts = df["source"].value_counts().reset_index()
                source_counts.columns = ["Fonte", "Quantidade"]
                
                fig_source = px.bar(
                    source_counts,
                    x="Fonte",
                    y="Quantidade",
                    color="Fonte",
                    text="Quantidade",
                    color_discrete_sequence=px.colors.qualitative.Prism
                )
                fig_source = apply_dark_theme(fig_source, height=320)
                fig_source.update_layout(showlegend=False, xaxis_title="", yaxis_title="Total de Vagas")
                st.plotly_chart(fig_source, use_container_width=True)

    # 4. Match Score Distribution
    with col4:
        with st.container(border=True):
            st.markdown("<div style='font-size: 16px; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;'>🎯 Distribuição de Match Scores (%)</div>", unsafe_allow_html=True)
            if "score" in df.columns:
                fig_score = px.histogram(
                    df,
                    x="score",
                    nbins=12,
                    color_discrete_sequence=["#2563EB"],
                    opacity=0.9
                )
                fig_score = apply_dark_theme(fig_score, height=320)
                fig_score.update_layout(xaxis_title="Match Score (%)", yaxis_title="Frequência")
                st.plotly_chart(fig_score, use_container_width=True)
