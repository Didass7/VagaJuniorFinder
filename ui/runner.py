import os
import sys
import subprocess
import time
import pandas as pd
import streamlit as st
from config import config, load_config
from ui.profiles import get_available_profiles

AVAILABLE_PORTALS = [
    ("LinkedIn Jobs (Guest API)", "linkedin", "🇵🇹"),
    ("ITJobs.pt (API / RSS)", "itjobs", "🇵🇹"),
    ("Carga de Trabalhos", "cargadetrabalhos", "🇵🇹"),
    ("Net-Empregos (TI & IEFP)", "netempregos", "🇵🇹"),
    ("IEFP Online (Estágios Oficiais)", "iefp", "🇵🇹"),
    ("Euraxess / Bolsas P&D", "euraxess", "🎓"),
    ("Landing.jobs", "landingjobs", "🇪🇺"),
    ("Jobicy (Data & AI)", "jobicy", "🌍"),
    ("Remotive (Tech Remote)", "remotive", "🌍"),
    ("RemoteOK", "remoteok", "🌐"),
    ("Arbeitnow (Europa & Remote)", "arbeitnow", "🇪🇺"),
    ("Jobspresso (Remote Tech)", "jobspresso", "☕"),
]

def render_runner(active_profile: str):
    st.markdown(
        """
        <div style="margin-bottom: 8px;">
            <h1 style="font-size: 26px; font-weight: 800; margin: 0; color: #F8FAFC; letter-spacing: -0.5px;">⚡ Execução de Pipeline On-Demand</h1>
            <div style="font-size: 13px; color: #94A3B8;">Extração multi-portal concorrente, deduplicação SHA-256 e avaliação semântica por LLM em tempo real.</div>
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
                "🎯 Candidato / Perfil Alvo:",
                options=all_options,
                index=all_options.index(active_profile) if active_profile in all_options else 1
            )
        with c2:
            st.write("")
            st.write("")
            dry_run = st.checkbox("🧪 Modo Dry-Run (não sincroniza com Notion)", value=False)

        st.markdown("<div style='font-size: 12px; font-weight: 700; color: #94A3B8; margin: 12px 0 6px 0;'>PORTAIS ATIVOS NA PIPELINE (12 FONTES PARALELAS)</div>", unsafe_allow_html=True)
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            for label, key, flag in AVAILABLE_PORTALS[:6]:
                st.markdown(f"<div style='font-size: 13px; color: #CBD5E1; margin-bottom: 4px;'>{flag} <b>{label}</b> &nbsp;<span style='color: #10B981; font-size: 10px; font-weight: 700;'>● ATIVO</span></div>", unsafe_allow_html=True)
        with col_p2:
            for label, key, flag in AVAILABLE_PORTALS[6:]:
                st.markdown(f"<div style='font-size: 13px; color: #CBD5E1; margin-bottom: 4px;'>{flag} <b>{label}</b> &nbsp;<span style='color: #10B981; font-size: 10px; font-weight: 700;'>● ATIVO</span></div>", unsafe_allow_html=True)

        st.write("")
        start_btn = st.button("🚀 Iniciar Pesquisa de Vagas Agora", type="primary", use_container_width=True)

    if start_btn:
        run_pipeline_execution(chosen_target, dry_run)

def run_pipeline_execution(target: str, dry_run: bool):
    st.write("")
    # macOS-style Terminal Box Header
    st.markdown(
        """
        <div style="background: #111827; border-top-left-radius: 10px; border-top-right-radius: 10px; padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; border: 1px solid rgba(255,255,255,0.08); border-bottom: none;">
            <div style="display: flex; gap: 6px; align-items: center;">
                <div style="width: 10px; height: 10px; border-radius: 50%; background: #EF4444;"></div>
                <div style="width: 10px; height: 10px; border-radius: 50%; background: #F59E0B;"></div>
                <div style="width: 10px; height: 10px; border-radius: 50%; background: #10B981;"></div>
            </div>
            <div style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #94A3B8; font-weight: 600;">vagajuniorfinder-runner ~ zsh</div>
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
            status_indicator.update(label=f"✅ Pipeline concluída com sucesso em {elapsed:.1f}s!", state="complete", expanded=False)
            st.success("🎉 Execução terminada! Novos dados estão disponíveis no Dashboard.")
            st.cache_data.clear()
        else:
            status_indicator.update(label=f"❌ Erro durante a execução (Código de saída: {rc})", state="error", expanded=True)
            st.error("Ocorreu um erro durante a execução da pipeline. Consulta os registos na consola acima.")

    except Exception as e:
        status_indicator.update(label="❌ Falha crítica ao iniciar o processo", state="error")
        st.error(f"Erro: {e}")
