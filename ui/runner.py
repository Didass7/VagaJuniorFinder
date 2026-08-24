import os
import sys
import subprocess
import time
import pandas as pd
import streamlit as st
from config import config, load_config
from ui.profiles import get_available_profiles

AVAILABLE_PORTALS = [
    ("LinkedIn Jobs (Guest API)", "linkedin"),
    ("ITJobs.pt (API / RSS)", "itjobs"),
    ("Carga de Trabalhos", "cargadetrabalhos"),
    ("Net-Empregos (TI & IEFP)", "netempregos"),
    ("IEFP Online (Estágios Oficiais)", "iefp"),
    ("Euraxess / Bolsas P&D", "euraxess"),
    ("Landing.jobs", "landingjobs"),
    ("Jobicy (Data & AI)", "jobicy"),
    ("Remotive (Tech Remote)", "remotive"),
    ("RemoteOK", "remoteok"),
    ("Arbeitnow (Europa & Remote)", "arbeitnow"),
    ("Jobspresso (Remote Tech)", "jobspresso"),
]

def render_runner(active_profile: str):
    st.header("⚡ Executar Pesquisa de Vagas On-Demand")
    st.markdown("Inicia a extração, deduplicação heurística e avaliação com IA em tempo real com registos detalhados.")

    profiles = get_available_profiles()
    all_options = ["Todos os Perfis"] + profiles

    c1, c2 = st.columns([2, 1])
    with c1:
        chosen_target = st.selectbox(
            "Candidato / Perfil Alvo:",
            options=all_options,
            index=all_options.index(active_profile) if active_profile in all_options else 1
        )
    with c2:
        st.write("")
        st.write("")
        dry_run = st.checkbox("Modo Dry-Run (não sincroniza com Notion)", value=False)

    with st.expander("🌐 Portais Ativos na Pesquisa", expanded=False):
        st.caption("Por omissão, todos os 12 portais de vagas são consultados em paralelo.")
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            for label, key in AVAILABLE_PORTALS[:6]:
                st.checkbox(label, value=True, key=f"portal_{key}", disabled=True)
        with col_p2:
            for label, key in AVAILABLE_PORTALS[6:]:
                st.checkbox(label, value=True, key=f"portal_{key}", disabled=True)

    st.divider()

    col_btn, _ = st.columns([2, 3])
    with col_btn:
        start_btn = st.button("🚀 Iniciar Pesquisa de Vagas", type="primary", use_container_width=True)

    if start_btn:
        run_pipeline_execution(chosen_target, dry_run)

def run_pipeline_execution(target: str, dry_run: bool):
    st.subheader("🖥️ Consola de Execução em Direto")
    log_container = st.empty()
    status_indicator = st.status("A executar a pesquisa de vagas...", expanded=True)
    
    logs = []
    
    # Determine script and environment
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
                # Keep last 50 lines rendered in real-time
                log_container.code("\n".join(logs[-50:]), language="log")

        rc = process.poll()
        elapsed = time.time() - start_time

        if rc == 0:
            status_indicator.update(label=f"✅ Pesquisa concluída com sucesso em {elapsed:.1f}s!", state="complete", expanded=False)
            st.success("Execução terminada sem erros!")
            st.cache_data.clear()
        else:
            status_indicator.update(label=f"❌ Erro durante a execução (Código de saída: {rc})", state="error", expanded=True)
            st.error("Aconteceu um erro durante a execução da pipeline. Consulta os logs acima.")

    except Exception as e:
        status_indicator.update(label="❌ Falha crítica ao iniciar o processo", state="error")
        st.error(f"Erro: {e}")
