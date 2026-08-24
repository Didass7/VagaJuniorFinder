import os
import re
from collections import Counter
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from ui.dashboard import load_all_jobs, STATUS_COLORS

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

def render_analytics(active_profile: str):
    st.header("📊 Métricas & Tendências de Mercado")
    st.markdown(f"Análise estatística e inteligência de mercado das vagas qualificadas para o candidato **`{active_profile}`**.")

    jobs = load_all_jobs(active_profile)
    if not jobs:
        st.info("Ainda não existem vagas registadas para analisar. Executa a pesquisa primeiro!")
        return

    df = pd.DataFrame(jobs)

    # ── Section 1: Candidacy Status Overview ──
    st.subheader("🎯 Progresso de Candidaturas (Funil do Notion)")
    if "status" in df.columns:
        st_counts = df["status"].value_counts().reset_index()
        st_counts.columns = ["Estado", "Total"]

        color_map = {k: v["bg"] for k, v in STATUS_COLORS.items()}

        fig_status = px.bar(
            st_counts,
            x="Estado",
            y="Total",
            color="Estado",
            text="Total",
            color_discrete_map=color_map
        )
        fig_status.update_layout(
            showlegend=False,
            margin=dict(l=20, r=20, t=20, b=20),
            height=300,
            xaxis_title="",
            yaxis_title="Número de Vagas"
        )
        st.plotly_chart(fig_status, use_container_width=True)

    st.divider()

    col1, col2 = st.columns(2)

    # 1. Tech Stack Frequency Bar Chart
    with col1:
        st.subheader("⚡ Tecnologias Mais Requisitadas")
        tech_counts = extract_tech_frequency(jobs)
        if tech_counts:
            top_techs = tech_counts.most_common(12)
            tech_df = pd.DataFrame(top_techs, columns=["Tecnologia", "Menções"]).sort_values(by="Menções", ascending=True)
            
            fig_tech = px.bar(
                tech_df,
                x="Menções",
                y="Tecnologia",
                orientation="h",
                color="Menções",
                color_continuous_scale="Viridis",
                text="Menções"
            )
            fig_tech.update_layout(
                showlegend=False,
                margin=dict(l=20, r=20, t=20, b=20),
                height=380,
                xaxis_title="Número de Vagas",
                yaxis_title=""
            )
            st.plotly_chart(fig_tech, use_container_width=True)
        else:
            st.caption("Sem dados de tecnologias disponíveis.")

    # 2. Work Mode Distribution Donut Chart
    with col2:
        st.subheader("📍 Modalidade de Trabalho")
        if "work_mode" in df.columns:
            mode_counts = df["work_mode"].value_counts().reset_index()
            mode_counts.columns = ["Modalidade", "Quantidade"]
            
            fig_mode = px.pie(
                mode_counts,
                values="Quantidade",
                names="Modalidade",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_mode.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                height=380
            )
            st.plotly_chart(fig_mode, use_container_width=True)
        else:
            st.caption("Sem dados de modalidades disponíveis.")

    st.divider()

    col3, col4 = st.columns(2)

    # 3. Source Portals Distribution
    with col3:
        st.subheader("🌐 Vagas por Portal de Origem")
        if "source" in df.columns:
            source_counts = df["source"].value_counts().reset_index()
            source_counts.columns = ["Fonte", "Quantidade"]
            
            fig_source = px.bar(
                source_counts,
                x="Fonte",
                y="Quantidade",
                color="Fonte",
                text="Quantidade",
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig_source.update_layout(
                showlegend=False,
                margin=dict(l=20, r=20, t=20, b=20),
                height=350,
                xaxis_title="",
                yaxis_title="Total de Vagas"
            )
            st.plotly_chart(fig_source, use_container_width=True)

    # 4. Match Score Distribution
    with col4:
        st.subheader("🎯 Distribuição dos Match Scores (%)")
        if "score" in df.columns:
            fig_score = px.histogram(
                df,
                x="score",
                nbins=12,
                color_discrete_sequence=["#3B82F6"],
                opacity=0.85
            )
            fig_score.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                height=350,
                xaxis_title="Match Score (%)",
                yaxis_title="Frequência"
            )
            st.plotly_chart(fig_score, use_container_width=True)
