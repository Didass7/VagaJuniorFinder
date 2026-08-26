import os
import sys
import subprocess
import time
import pandas as pd
import streamlit as st
from config import config, load_config
from ui.profiles import get_available_profiles

AVAILABLE_PORTALS = [
    ("LinkedIn Jobs (Guest API)", "linkedin", "🇵🇹 PT"),
    ("ITJobs.pt (API / RSS)", "itjobs", "🇵🇹 PT"),
    ("Indeed Portugal", "indeed", "🇵🇹 PT"),
    ("Sapo Emprego (TI & Estágios)", "sapo", "🇵🇹 PT"),
    ("Teamlyzer Jobs (Tech & Salários)", "teamlyzer", "🇵🇹 PT"),
    ("Net-Empregos (TI & IEFP)", "netempregos", "🇵🇹 PT"),
    ("IEFP Online (Estágios Oficiais)", "iefp", "🇵🇹 PT"),
    ("Carga de Trabalhos", "cargadetrabalhos", "🇵🇹 PT"),
    ("Euraxess / Bolsas P&D", "euraxess", "🔬 I&D"),
    ("Landing.jobs", "landingjobs", "🇪🇺 EU"),
    ("Arbeitnow (Europa & Remote)", "arbeitnow", "🇪🇺 EU"),
    ("Jobicy (Data & AI)", "jobicy", "🌍 Global"),
    ("Remotive (Tech Remote)", "remotive", "🌍 Global"),
    ("RemoteOK", "remoteok", "🌍 Global"),
    ("Jobspresso (Remote Tech)", "jobspresso", "🌍 Global"),
]

def render_runner(active_profile: str):
    st.markdown(
        """
        <div style="margin-bottom: 8px;">
            <h1 style="font-size: 24px; font-weight: 800; margin: 0; color: #F8FAFC; letter-spacing: -0.5px;">Execução da Pipeline</h1>
            <div style="font-size: 13px; color: #94A3B8; margin-top: 2px;">Extração multi-portal concorrente, deduplicação SHA-256 e avaliação semântica por LLM em tempo real.</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.divider()

    profiles = get_available_profiles()
    all_options = ["Todos os Perfis"] + profiles

    with st.container(border=True):
        c1, c2 = st.columns([2.5, 1.5])
        with c1:
            chosen_target = st.selectbox(
                "Perfil Alvo",
                options=all_options,
                index=all_options.index(active_profile) if active_profile in all_options else 1
            )
        with c2:
            st.write("")
            st.write("")
            dry_run = st.checkbox("Modo Simulação / Dry-Run (não sincroniza com Notion)", value=False)

        st.markdown(f"<div style='font-size: 11px; font-weight: 700; color: #94A3B8; margin: 12px 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px;'>Portais Ativos na Pipeline ({len(AVAILABLE_PORTALS)} Fontes Concorrentes)</div>", unsafe_allow_html=True)
        col_p1, col_p2 = st.columns(2)
        mid = (len(AVAILABLE_PORTALS) + 1) // 2
        with col_p1:
            for label, key, tag in AVAILABLE_PORTALS[:mid]:
                st.markdown(
                    f"""
                    <div style='font-size: 13px; color: #CBD5E1; margin-bottom: 5px; display: flex; align-items: center;'>
                        <span style='background: rgba(30, 41, 59, 0.7); color: #94A3B8; border: 1px solid rgba(255, 255, 255, 0.08); padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; margin-right: 8px; min-width: 24px; text-align: center;'>{tag}</span>
                        <b>{label}</b> &nbsp;<span style='color: #10B981; font-size: 10px; font-weight: 600; margin-left: auto;'>● Ativo</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        with col_p2:
            for label, key, tag in AVAILABLE_PORTALS[mid:]:
                st.markdown(
                    f"""
                    <div style='font-size: 13px; color: #CBD5E1; margin-bottom: 5px; display: flex; align-items: center;'>
                        <span style='background: rgba(30, 41, 59, 0.7); color: #94A3B8; border: 1px solid rgba(255, 255, 255, 0.08); padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; margin-right: 8px; min-width: 24px; text-align: center;'>{tag}</span>
                        <b>{label}</b> &nbsp;<span style='color: #10B981; font-size: 10px; font-weight: 600; margin-left: auto;'>● Ativo</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        st.write("")
        start_btn = st.button("Iniciar Execução da Pipeline", type="primary", use_container_width=True)

    if start_btn:
        run_pipeline_execution(chosen_target, dry_run)

def run_pipeline_execution(target: str, dry_run: bool):
    st.write("")
    # Minimalist Console Box Header
    st.markdown(
        """
        <div style="background: #0F172A; border-top-left-radius: 8px; border-top-right-radius: 8px; padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; border: 1px solid rgba(255,255,255,0.08); border-bottom: none;">
            <div style="display: flex; gap: 6px; align-items: center;">
                <div style="width: 8px; height: 8px; border-radius: 50%; background: #EF4444; opacity: 0.8;"></div>
                <div style="width: 8px; height: 8px; border-radius: 50%; background: #F59E0B; opacity: 0.8;"></div>
                <div style="width: 8px; height: 8px; border-radius: 50%; background: #10B981; opacity: 0.8;"></div>
            </div>
            <div style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #94A3B8; font-weight: 500;">pipeline-runner ~ bash</div>
            <div style="width: 30px;"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    log_container = st.empty()
    status_indicator = st.status("A executar a pipeline de extração e avaliação...", expanded=True)
    
    logs = []
    python_exe = sys.executable
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    if target == "Todos os Perfis":
        cmd = [python_exe, "run_all.py"]
    else:
        cmd = [python_exe, "main.py"]
        env["ACTIVE_PROFILE"] = target
        
    if dry_run:
        cmd.append("--dry-run")

    start_time = time.time()
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            encoding="utf-8",
            errors="replace"
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                logs.append(line.rstrip())
                log_container.code("\n".join(logs[-45:]), language="log")

        rc = process.poll()
        elapsed = time.time() - start_time

        if rc == 0:
            status_indicator.update(label=f"Pipeline concluída com sucesso em {elapsed:.1f}s.", state="complete", expanded=False)
            st.success("Execução terminada. Novos dados disponíveis no Dashboard.")
            st.cache_data.clear()
        else:
            status_indicator.update(label=f"Erro na execução (Código de saída: {rc})", state="error", expanded=True)
            st.error("Ocorreu um erro durante a execução da pipeline. Consulte os registos acima.")

    except Exception as e:
        status_indicator.update(label="Falha ao iniciar o processo", state="error")
        st.error(f"Erro: {e}")

