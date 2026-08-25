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

# ── SaaS Premium Design System & CSS ──
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    /* ── Typography & Reset ── */
    html, body, p, h1, h2, h3, h4, h5, h6, label, .stMarkdown p, .stButton button, .stTextInput input, .stTextArea textarea {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Main Canvas Background ── */
    .stApp {
        background: radial-gradient(circle at 15% 10%, rgba(37, 99, 235, 0.08) 0%, transparent 45%),
                    radial-gradient(circle at 85% 80%, rgba(139, 92, 246, 0.06) 0%, transparent 45%),
                    #0B0F17 !important;
        color: #F1F5F9;
    }

    /* ── Top Header / Block Container Spacing ── */
    .block-container {
        padding-top: 1.75rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px;
    }

    /* ── Glassmorphism Containers & Cards ── */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(15, 23, 42, 0.65) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        border-radius: 14px !important;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.35) !important;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(59, 130, 246, 0.35) !important;
        box-shadow: 0 8px 30px -4px rgba(37, 99, 235, 0.15) !important;
    }

    /* ── Metric Cards Premium Styling ── */
    div[data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.7) !important;
        backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2) !important;
        transition: transform 0.15s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: rgba(59, 130, 246, 0.3) !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 13px !important;
        font-weight: 600 !important;
        color: #94A3B8 !important;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 800 !important;
        color: #F8FAFC !important;
        letter-spacing: -0.5px;
    }

    /* ── Buttons Styling ── */
    .stButton>button {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 9px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 0.5rem 1rem !important;
        box-shadow: 0 2px 10px rgba(37, 99, 235, 0.3) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .stButton>button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(37, 99, 235, 0.5) !important;
        border-color: rgba(255, 255, 255, 0.3) !important;
    }
    .stButton>button:active {
        transform: translateY(0) !important;
    }
    .stLinkButton>a {
        border-radius: 9px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        transition: all 0.15s ease !important;
    }

    /* ── Form Inputs & Selectboxes ── */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div {
        background: rgba(15, 23, 42, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 8px !important;
        color: #F1F5F9 !important;
        font-size: 14px !important;
    }
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25) !important;
    }

    /* ── Sidebar Redesign ── */
    section[data-testid="stSidebar"] {
        background-color: #080C14 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        padding-bottom: 8px;
    }
    .sidebar-brand-icon {
        font-size: 26px;
        line-height: 1;
    }
    .sidebar-brand-text {
        font-size: 18px;
        font-weight: 800;
        letter-spacing: -0.3px;
        color: #F8FAFC;
    }
    .profile-card {
        background: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 12px 14px;
        margin-top: 6px;
    }
    .profile-avatar {
        width: 36px;
        height: 36px;
        border-radius: 8px;
        background: linear-gradient(135deg, #2563EB, #7C3AED);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        color: white;
        font-size: 15px;
    }

    /* ── Status Pills / Radio Navigation ── */
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        gap: 8px !important;
        padding: 4px !important;
        background: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        border-radius: 12px !important;
    }
    div[data-testid="stRadio"] label {
        padding: 6px 14px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        transition: all 0.15s ease !important;
    }

    /* ── Expanders ── */
    div[data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.5) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
    }

    /* ── Scrollbars ── */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #0B0F17;
    }
    ::-webkit-scrollbar-thumb {
        background: #1E293B;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #334155;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-icon">🎯</div>
                <div>
                    <div class="sidebar-brand-text">VagaJuniorFinder</div>
                    <div style="font-size: 11px; color: #64748B; font-weight: 500;">AI Job Intelligence Hub</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.divider()

        # Profile Selection
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

        # Candidate Glass Card
        prof_data = load_profile_data(selected_profile).get("candidate", {})
        if prof_data:
            initials = "".join([part[0].upper() for part in prof_data.get('name', selected_profile).split()[:2]]) or "DO"
            iefp_badge = '<span style="background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700;">IEFP ATIVAR.PT</span>' if prof_data.get("iefp_eligible") else ''
            
            st.markdown(
                f"""
                <div class="profile-card">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div class="profile-avatar">{initials}</div>
                        <div style="overflow: hidden;">
                            <div style="font-weight: 700; color: #F8FAFC; font-size: 14px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{prof_data.get('name', selected_profile)}</div>
                            <div style="font-size: 11px; color: #94A3B8; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">🎓 {prof_data.get('degree', 'Engenharia')[:30]}...</div>
                        </div>
                    </div>
                    <div style="margin-top: 8px; display: flex; gap: 6px; align-items: center;">
                        {iefp_badge}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

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
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.3); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 10px; font-size: 11px; color: #94A3B8;">
                <div style="font-weight: 600; color: #CBD5E1; margin-bottom: 2px;">☁️ Automação Cloud</div>
                Execuções diárias automáticas às 09:00 e 21:00 via GitHub Actions.
            </div>
            """,
            unsafe_allow_html=True
        )

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
