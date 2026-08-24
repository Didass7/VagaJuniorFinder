import os
import requests
import streamlit as st
from config import config, load_config

def render_settings():
    st.header("⚙️ Diagnóstico & Configurações")
    st.markdown("Verifica o estado das variáveis de ambiente, integrações de APIs e configurações ativas do sistema.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔑 Estado das Credenciais (API Keys)")
        
        # Notion
        has_notion_token = bool(config.notion_token)
        has_notion_db = bool(config.notion_database_id)
        if has_notion_token and has_notion_db:
            st.success("🟢 **Notion API**: Configurado (Token & Database ID presentes)")
        elif has_notion_token:
            st.warning("🟡 **Notion API**: Token configurado, mas Database ID em falta")
        else:
            st.error("🔴 **Notion API**: Não configurado")

        # Groq
        if config.groq_api_key:
            st.success(f"🟢 **Groq LLM**: Configurado (Modelo: `{config.groq_model_name}`)")
        else:
            st.warning("🟡 **Groq LLM**: Sem chave de API (usará Gemini como fallback)")

        # Gemini
        if config.gemini_api_key:
            st.success(f"🟢 **Google Gemini**: Configurado (Modelo: `{config.ai_model_name}`)")
        else:
            st.warning("🟡 **Google Gemini**: Sem chave de API")

        # ITJobs
        if config.itjobs_api_key:
            st.success("🟢 **ITJobs.pt API**: Chave configurada")
        else:
            st.info("ℹ️ **ITJobs.pt**: Sem chave de API (usará feeds RSS públicos)")

    with col2:
        st.subheader("🌐 Teste de Conexões em Tempo Real")
        if st.button("🔄 Executar Teste de Conectividade", use_container_width=True):
            with st.spinner("A testar conexões com os serviços..."):
                results = test_all_connections()
                for service, (ok, msg) in results.items():
                    if ok:
                        st.success(f"**{service}**: {msg}")
                    else:
                        st.error(f"**{service}**: {msg}")

    st.divider()

    st.subheader("📁 Ficheiros e Diretórios do Projeto")
    info_col1, info_col2, info_col3 = st.columns(3)
    
    profiles_count = len(os.listdir("profiles")) if os.path.exists("profiles") else 0
    cache_exists = os.path.exists(config.cache_file)
    
    with info_col1:
        st.metric("Perfis Encontrados", f"{profiles_count} perfis")
    with info_col2:
        st.metric("Cache de Vagas", "Ativo" if cache_exists else "Vazio")
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
                results["Notion API"] = (True, f"Conectado com sucesso à base '{title}'!")
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
