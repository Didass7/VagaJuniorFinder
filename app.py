import os
import sys
import streamlit as st
from config import config, load_config
from ui.dashboard import render_dashboard
from ui.runner import render_runner
from ui.profiles import render_profiles, get_available_profiles, load_profile_data
from ui.analytics import render_analytics
from ui.settings import render_settings

# ── Streamlit Page Configuration ──
st.set_page_config(
    page_title="VagaJuniorFinder — AI Job Hub",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS for Modern Styling ──
st.markdown("""
<style>
    /* Main container styling */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    /* Metric card improvements */
    div[data-testid="stMetricValue"] {
        font-size: 26px;
        font-weight: 700;
        color: #2563EB;
    }
    /* Buttons */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    /* Sidebar header */
    .sidebar-header {
        font-size: 20px;
        font-weight: 800;
        margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # ── Sidebar ──
    with st.sidebar:
        st.markdown("<div class='sidebar-header'>🎯 VagaJuniorFinder</div>", unsafe_allow_html=True)
        st.caption("Automação Inteligente de Vagas Tech & IA")
        st.divider()

        # Profile selection
        profiles = get_available_profiles()
        if "active_profile" not in st.session_state:
            st.session_state["active_profile"] = profiles[0] if profiles else "diogo_ai"

        selected_profile = st.selectbox(
            "👤 Candidato Ativo:",
            options=profiles if profiles else ["diogo_ai"],
            index=profiles.index(st.session_state["active_profile"]) if st.session_state["active_profile"] in profiles else 0,
            key="sidebar_active_profile"
        )
        st.session_state["active_profile"] = selected_profile

        # Candidate Mini-Card
        prof_data = load_profile_data(selected_profile).get("candidate", {})
        if prof_data:
            with st.container(border=True):
                st.markdown(f"**{prof_data.get('name', selected_profile)}**")
                st.caption(f"🎓 {prof_data.get('degree', 'Não especificado')[:45]}...")
                if prof_data.get("iefp_eligible"):
                    st.markdown('<span style="background-color: #064E3B; color: #34D399; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">✅ IEFP ELEGÍVEL</span>', unsafe_allow_html=True)

        st.divider()

        # Navigation
        menu_choice = st.radio(
            "Navegação:",
            [
                "🏠 Feed & Dashboard",
                "⚡ Executar Pesquisa",
                "👤 Gestor de Perfis",
                "📊 Métricas & Mercado",
                "⚙️ Configurações & APIs"
            ],
            index=0
        )

        st.divider()
        st.caption("💡 Executa diariamente às 09:00 e 21:00 via GitHub Actions.")

    # ── Main Content Router ──
    if menu_choice == "🏠 Feed & Dashboard":
        render_dashboard(st.session_state["active_profile"])
    elif menu_choice == "⚡ Executar Pesquisa":
        render_runner(st.session_state["active_profile"])
    elif menu_choice == "👤 Gestor de Perfis":
        render_profiles()
    elif menu_choice == "📊 Métricas & Mercado":
        render_analytics(st.session_state["active_profile"])
    elif menu_choice == "⚙️ Configurações & APIs":
        render_settings()

if __name__ == "__main__":
    main()
