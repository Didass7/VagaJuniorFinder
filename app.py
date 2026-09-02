import os
import sys
import html
import streamlit as st
from core.config import config, load_config
from ui.dashboard import render_dashboard
from ui.runner import render_runner
from ui.profiles import render_profiles, get_available_profiles, load_profile_data
from ui.analytics import render_analytics
from ui.settings import render_settings

# ── Streamlit Page Configuration ──
st.set_page_config(
    page_title="VagaJuniorFinder | Career Intelligence Hub",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Executive Clean SaaS Design System & CSS ──
from pathlib import Path

# -- Executive Clean SaaS Design System & CSS --
try:
    css_path = Path(__file__).parent / "ui" / "styles.css"
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
except Exception as e:
    import logging
    logging.warning(f"Failed to load styles.css: {e}")
    css_content = ""

st.markdown(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
{css_content}
</style>
""", unsafe_allow_html=True)

LAST_PROFILE_FILE = os.path.join("data", ".last_selected_profile")

def get_last_selected_profile(available_profiles: list[str]) -> str:
    if hasattr(st, "query_params") and "profile" in st.query_params:
        qp = st.query_params.get("profile")
        if qp and qp in available_profiles:
            return qp
    if os.path.exists(LAST_PROFILE_FILE):
        try:
            with open(LAST_PROFILE_FILE, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if saved and saved in available_profiles:
                    return saved
        except Exception:
            pass
    return "diogo" if "diogo" in available_profiles else (available_profiles[0] if available_profiles else "diogo")

def save_last_selected_profile(profile_name: str):
    if not profile_name:
        return
    try:
        os.makedirs("data", exist_ok=True)
        with open(LAST_PROFILE_FILE, "w", encoding="utf-8") as f:
            f.write(profile_name.strip())
        if hasattr(st, "query_params"):
            st.query_params["profile"] = profile_name
    except Exception:
        pass

def main():
    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-logo">VF</div>
                <div>
                    <div class="sidebar-brand-text">VagaJuniorFinder</div>
                    <div style="font-size: 11px; color: #64748B; font-weight: 500;">Career Intelligence Platform</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.divider()

        # Profile Selection (Persistent)
        profiles = get_available_profiles()
        if "active_profile" not in st.session_state:
            st.session_state["active_profile"] = get_last_selected_profile(profiles)

        cur_prof = st.session_state["active_profile"]
        default_idx = profiles.index(cur_prof) if cur_prof in profiles else 0

        selected_profile = st.selectbox(
            "Candidato Ativo",
            options=profiles if profiles else ["diogo"],
            index=default_idx,
            key="sidebar_active_profile"
        )
        if selected_profile != st.session_state["active_profile"]:
            st.session_state["active_profile"] = selected_profile
            save_last_selected_profile(selected_profile)
            st.rerun()
        else:
            save_last_selected_profile(selected_profile)

        # Candidate Clean Card
        prof_data = load_profile_data(selected_profile).get("candidate", {})
        if prof_data:
            c_name = html.escape(str(prof_data.get('name', selected_profile)))
            c_degree = html.escape(str(prof_data.get('degree', 'Licenciatura')[:30]))
            initials = html.escape("".join([part[0].upper() for part in prof_data.get('name', selected_profile).split()[:2]]) or "VF")
            iefp_badge = '<span style="background: rgba(16, 185, 129, 0.12); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.25); padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: 0.3px;">IEFP ATIVAR.PT</span>' if prof_data.get("iefp_eligible") else ''
            
            st.markdown(
                f"""
                <div class="profile-card">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div class="profile-avatar">{initials}</div>
                        <div style="overflow: hidden;">
                            <div style="font-weight: 700; color: #F8FAFC; font-size: 13px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{c_name}</div>
                            <div style="font-size: 11px; color: #94A3B8; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{c_degree}</div>
                        </div>
                    </div>
                    {f'<div style="margin-top: 8px;">{iefp_badge}</div>' if iefp_badge else ''}
                </div>
                """,
                unsafe_allow_html=True
            )

        st.divider()

        # Navigation without emojis
        menu_choice = st.radio(
            "Navegação",
            [
                "Feed & Dashboard",
                "Executar Pipeline",
                "Gestor de Perfis",
                "Métricas & Mercado",
                "Configurações & APIs"
            ],
            index=0
        )

        st.divider()
        st.markdown(
            """
            <div style="background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 10px 12px; font-size: 11px; color: #94A3B8;">
                <div style="font-weight: 600; color: #CBD5E1; margin-bottom: 2px; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px;">Automação Agendada</div>
                Execuções automáticas às 09:00 e 21:00 UTC via GitHub Actions.
            </div>
            """,
            unsafe_allow_html=True
        )

    # ── Main Content Router ──
    if menu_choice == "Feed & Dashboard":
        render_dashboard(st.session_state["active_profile"])
    elif menu_choice == "Executar Pipeline":
        render_runner(st.session_state["active_profile"])
    elif menu_choice == "Gestor de Perfis":
        render_profiles()
    elif menu_choice == "Métricas & Mercado":
        render_analytics(st.session_state["active_profile"])
    elif menu_choice == "Configurações & APIs":
        render_settings()

if __name__ == "__main__":
    main()

