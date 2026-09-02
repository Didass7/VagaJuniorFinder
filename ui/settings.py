import os
import requests
import streamlit as st
from core.config import config, load_config

def render_settings():
    st.markdown(
        """
        <div style="margin-bottom: 8px;">
            <h1 style="font-size: 24px; font-weight: 800; margin: 0; color: #F8FAFC; letter-spacing: -0.5px;">Diagnóstico & Definições</h1>
            <div style="font-size: 13px; color: #94A3B8; margin-top: 2px;">Monitorização do estado das variáveis de ambiente, integrações de APIs e armazenamento local.</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("<div style='font-size: 13px; font-weight: 700; color: #CBD5E1; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;'>Estado das Credenciais e Integrações</div>", unsafe_allow_html=True)
            
            # Notion
            has_notion_token = bool(config.notion_token)
            has_notion_db = bool(config.notion_database_id)
            if has_notion_token and has_notion_db:
                st.markdown("<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#10B981; font-size:11px;'>●</span> Notion API</span><span style='font-size:12px; color:#A7F3D0;'>Token & DB Configurados</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#EF4444; font-size:11px;'>●</span> Notion API</span><span style='font-size:12px; color:#FECACA;'>Não Configurado</span></div>", unsafe_allow_html=True)

            # Groq
            if config.groq_api_key:
                st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#10B981; font-size:11px;'>●</span> Groq LLM</span><span style='font-size:12px; color:#A7F3D0;'>{config.groq_model_name}</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#F59E0B; font-size:11px;'>●</span> Groq LLM</span><span style='font-size:12px; color:#FDE68A;'>Sem chave (Fallback ativo)</span></div>", unsafe_allow_html=True)

            # Gemini
            if config.gemini_api_key:
                st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#10B981; font-size:11px;'>●</span> Google Gemini</span><span style='font-size:12px; color:#A7F3D0;'>{config.ai_model_name}</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#F59E0B; font-size:11px;'>●</span> Google Gemini</span><span style='font-size:12px; color:#FDE68A;'>Sem chave</span></div>", unsafe_allow_html=True)

            # ITJobs
            if config.itjobs_api_key:
                st.markdown("<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); padding: 10px 14px; border-radius: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#10B981; font-size:11px;'>●</span> ITJobs.pt API</span><span style='font-size:12px; color:#A7F3D0;'>Chave Configurada</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='display:flex; justify-content:space-between; align-items:center; background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.25); padding: 10px 14px; border-radius: 8px;'><span style='font-weight:600; color:#E2E8F0; display:flex; align-items:center; gap:8px;'><span style='color:#3B82F6; font-size:11px;'>●</span> ITJobs.pt</span><span style='font-size:12px; color:#BFDBFE;'>Feeds RSS Públicos</span></div>", unsafe_allow_html=True)

    with col2:
        with st.container(border=True):
            st.markdown("<div style='font-size: 13px; font-weight: 700; color: #CBD5E1; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;'>Teste de Conectividade</div>", unsafe_allow_html=True)
            if st.button("Testar Conexões às APIs", type="primary", use_container_width=True):
                with st.spinner("A verificar conexões com servidores externos..."):
                    results = test_all_connections()
                    for service, (ok, msg) in results.items():
                        if ok:
                            st.success(f"**{service}**: {msg}")
                        else:
                            st.error(f"**{service}**: {msg}")
            else:
                st.caption("Envie requisições de teste para validar o acesso às APIs configuradas.")

    st.write("")

    with st.container(border=True):
        st.markdown("<div style='font-size: 13px; font-weight: 700; color: #CBD5E1; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;'>Armazenamento Local & Sincronização</div>", unsafe_allow_html=True)
        info_col1, info_col2, info_col3 = st.columns(3)
        
        profiles_count = len(os.listdir("profiles")) if os.path.exists("profiles") else 0
        cache_exists = os.path.exists(config.cache_file)
        
        with info_col1:
            st.metric("Perfis Armazenados", f"{profiles_count} candidatos")
        with info_col2:
            st.metric("Cache Deduplicação", "Ativo" if cache_exists else "Vazio")
        with info_col3:
            st.metric("Sincronização Notion", "Ativada" if config.enable_notion_sync else "Desativada")

def test_all_connections():
    results = {}
    
    # 1. Test Notion
    if config.notion_token and config.notion_database_id:
        try:
            url = f"https://api.notion.com/v1/databases/{config.notion_database_id}"
            headers = {
                "Authorization": f"Bearer {config.notion_token}",
                "Notion-Version": "2022-06-28",
            }
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                title = resp.json().get("title", [{}])[0].get("text", {}).get("content", "Base de Dados")
                results["Notion API"] = (True, f"Conectado com sucesso à base '{title}'.")
            else:
                results["Notion API"] = (False, f"Erro ({resp.status_code}): {resp.text[:100]}")
        except Exception as e:
            results["Notion API"] = (False, f"Falha de conexão: {str(e)}")
    else:
        results["Notion API"] = (False, "Chaves NOTION_TOKEN ou NOTION_DATABASE_ID em falta no .env")

    # 2. Test Groq
    if config.groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=config.groq_api_key)
            completion = client.chat.completions.create(
                model=config.groq_model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            results["Groq API"] = (True, f"Operacional com modelo {config.groq_model_name}")
        except Exception as e:
            results["Groq API"] = (False, f"Erro Groq: {str(e)}")
    else:
        results["Groq API"] = (False, "GROQ_API_KEY não configurada")

    # 3. Test Gemini
    if config.gemini_api_key:
        try:
            import google.genai as genai
            client = genai.Client(api_key=config.gemini_api_key)
            resp = client.models.generate_content(
                model=config.ai_model_name,
                contents="ping"
            )
            results["Google Gemini API"] = (True, f"Operacional com modelo {config.ai_model_name}")
        except Exception as e:
            results["Google Gemini API"] = (False, f"Erro Gemini: {str(e)}")
    else:
        results["Google Gemini API"] = (False, "GEMINI_API_KEY não configurada")

    return results
