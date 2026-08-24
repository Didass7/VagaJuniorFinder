import os
import json
import glob
import streamlit as st

PROFILES_DIR = "profiles"

def get_available_profiles():
    if not os.path.exists(PROFILES_DIR):
        os.makedirs(PROFILES_DIR, exist_ok=True)
    files = glob.glob(os.path.join(PROFILES_DIR, "*.json"))
    return [os.path.splitext(os.path.basename(f))[0] for f in sorted(files)]

def load_profile_data(profile_name: str) -> dict:
    filepath = os.path.join(PROFILES_DIR, f"{profile_name}.json")
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao ler perfil {profile_name}: {e}")
        return {}

def save_profile_data(profile_name: str, data: dict) -> bool:
    filepath = os.path.join(PROFILES_DIR, f"{profile_name}.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Erro ao guardar perfil: {e}")
        return False

def render_profiles():
    st.header("👤 Gestor de Perfis de Candidatos")
    st.markdown("Configura critérios de pesquisa personalizados, títulos-alvo, *stack* técnica e preferências para cada candidato.")

    profiles = get_available_profiles()
    
    col_sel, col_new = st.columns([3, 1])
    
    with col_sel:
        selected_profile = st.selectbox(
            "Selecionar Perfil para Editar:",
            options=profiles if profiles else ["diogo_ai"],
            index=0 if profiles else 0,
            key="profile_select_box"
        )

    with col_new:
        st.write("")
        st.write("")
        with st.popover("➕ Novo Perfil"):
            new_name = st.text_input("ID do Novo Perfil (ex: maria_data):", key="new_profile_name").strip().lower().replace(" ", "_")
            clone_from = st.selectbox("Copiar definições de:", options=["Em Branco"] + profiles, key="clone_from_profile")
            
            if st.button("Criar Perfil", use_container_width=True):
                if new_name and f"{new_name}.json" not in [os.path.basename(p) for p in glob.glob(os.path.join(PROFILES_DIR, "*.json"))]:
                    if clone_from != "Em Branco":
                        base_data = load_profile_data(clone_from)
                    else:
                        base_data = {
                            "candidate": {
                                "name": "Novo Candidato",
                                "email": "candidato@email.com",
                                "degree": "Licenciatura",
                                "iefp_eligible": True,
                                "languages": ["Português (Nativo)", "Inglês (B2)"],
                                "search_queries": ["python", "junior"],
                                "target_titles": ["Junior Developer"],
                                "tech_stack": ["python", "git", "sql"],
                                "junior_boosters": ["junior", "estágio", "trainee"],
                                "locations": ["portugal", "remoto"]
                            },
                            "notion_database_id": ""
                        }
                    if save_profile_data(new_name, base_data):
                        st.success(f"Perfil '{new_name}' criado!")
                        st.rerun()
                elif not new_name:
                    st.error("Nome de perfil inválido.")
                else:
                    st.warning("Já existe um perfil com esse nome.")

    if not selected_profile:
        st.info("Nenhum perfil selecionado.")
        return

    data = load_profile_data(selected_profile)
    candidate = data.get("candidate", {})

    st.divider()

    with st.form(f"edit_profile_form_{selected_profile}"):
        st.subheader(f"📝 Editar Perfil: `{selected_profile}`")

        # 1. Informações Pessoais
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Nome Completo:", value=candidate.get("name", ""))
            degree = st.text_input("Grau Académico / Formação:", value=candidate.get("degree", ""))
        with c2:
            email = st.text_input("Email de Contacto:", value=candidate.get("email", ""))
            iefp_eligible = st.checkbox("Elegível para Estágio IEFP / ATIVAR.pt", value=candidate.get("iefp_eligible", False))
        with c3:
            notion_id = st.text_input("Notion Database ID (Opcional):", value=data.get("notion_database_id", ""), help="Deixa em branco para usar o ID global do .env")
            languages_str = st.text_input("Idiomas (separados por vírgula):", value=", ".join(candidate.get("languages", [])))

        st.markdown("---")
        
        # 2. Critérios de Busca e Correspondência
        st.subheader("🎯 Critérios de Filtro e Matching")
        
        c4, c5 = st.columns(2)
        with c4:
            search_queries_text = st.text_area(
                "🔍 Termos de Pesquisa nos Scrapers (um por linha):",
                value="\n".join(candidate.get("search_queries", [])),
                height=130,
                help="Termos usados nas APIs e pesquisas públicas (ex: python, data, machine learning, estagio iefp)"
            )
            
            target_titles_text = st.text_area(
                "💼 Cargos-Alvo / Títulos Válidos (um por linha):",
                value="\n".join(candidate.get("target_titles", [])),
                height=200,
                help="Títulos aceites pelo filtro heurístico (ex: Junior AI Engineer, Cientista de Dados, Python Developer)"
            )

        with c5:
            tech_stack_text = st.text_area(
                "⚡ Tech Stack / Tecnologias Relevantes (uma por linha):",
                value="\n".join(candidate.get("tech_stack", [])),
                height=130,
                help="Tecnologias que aumentam a pontuação da vaga (ex: python, sql, fastapi, langchain, duckdb)"
            )

            junior_boosters_text = st.text_area(
                "🎓 Palavras-Chave de Nível Júnior (uma por linha):",
                value="\n".join(candidate.get("junior_boosters", [])),
                height=130,
                help="Termos que identificam nível inicial (ex: junior, entry level, trainee, estagio, iefp, recem-licenciado)"
            )

            locations_text = st.text_area(
                "📍 Localizações e Modalidades Permitidas (uma por linha):",
                value="\n".join(candidate.get("locations", [])),
                height=100,
                help="Cidades ou modalidades válidas (ex: portugal, lisboa, porto, remoto, hybrid)"
            )

        submitted = st.form_submit_button("💾 Guardar Alterações do Perfil", type="primary", use_container_width=True)

        if submitted:
            def parse_lines(text: str) -> list[str]:
                return [line.strip().lower() for line in text.split("\n") if line.strip()]

            def parse_titles(text: str) -> list[str]:
                return [line.strip() for line in text.split("\n") if line.strip()]

            def parse_csv(text: str) -> list[str]:
                return [x.strip() for x in text.split(",") if x.strip()]

            updated_data = {
                "candidate": {
                    "name": name.strip(),
                    "email": email.strip(),
                    "degree": degree.strip(),
                    "iefp_eligible": iefp_eligible,
                    "languages": parse_csv(languages_str),
                    "search_queries": parse_lines(search_queries_text),
                    "target_titles": parse_titles(target_titles_text),
                    "tech_stack": parse_lines(tech_stack_text),
                    "junior_boosters": parse_lines(junior_boosters_text),
                    "locations": parse_lines(locations_text)
                },
                "notion_database_id": notion_id.strip()
            }

            if save_profile_data(selected_profile, updated_data):
                st.success(f"✅ Perfil '{selected_profile}' guardado com sucesso!")
                st.rerun()
