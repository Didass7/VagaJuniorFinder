import os
import sys
import html
import streamlit as st
from config import config, load_config
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
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    /* ── Hide Streamlit Default Chrome & Allow Sidebar Toggle ── */
    #MainMenu, footer, div[data-testid="stDecoration"], div[data-testid="stToolbarActions"], div[data-testid="stStatusWidget"] {
        display: none !important;
        visibility: hidden !important;
    }
    header[data-testid="stHeader"], header.stAppHeader {
        background: transparent !important;
        height: auto !important;
        min-height: 2.5rem !important;
        z-index: 999 !important;
        pointer-events: auto !important;
    }
    div[data-testid="stToolbar"], div.stAppToolbar {
        background: transparent !important;
        right: 1rem !important;
        height: auto !important;
        pointer-events: auto !important;
    }
    
    /* ── Close Sidebar Button (Perfect Alignment on same row as Brand Logo) ── */
    section[data-testid="stSidebar"] div[data-testid="stSidebarHeader"] {
        position: absolute !important;
        top: 0.9rem !important;
        right: 0.75rem !important;
        z-index: 100 !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent !important;
        height: auto !important;
        min-height: 0 !important;
        width: auto !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] button {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 6px !important;
        color: #94A3B8 !important;
        padding: 4px 6px !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: none !important;
        transition: all 0.15s ease !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] button:hover {
        color: #38BDF8 !important;
        background: #1E293B !important;
        border-color: rgba(56, 189, 248, 0.3) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {
        padding-top: 0.9rem !important;
    }

    /* ── Reopen Sidebar Button (When sidebar is collapsed) ── */
    div[data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display: inline-flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    div[data-testid="stSidebarCollapsedControl"] button,
    [data-testid="collapsedControl"] button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: #0C1220 !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 6px !important;
        color: #94A3B8 !important;
        padding: 4px 6px !important;
        margin: 4px 0 0 8px !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25) !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stSidebarCollapsedControl"] button:hover,
    [data-testid="collapsedControl"] button:hover {
        background: #1E293B !important;
        color: #38BDF8 !important;
        border-color: rgba(56, 189, 248, 0.4) !important;
    }
    div[data-testid="stSidebarCollapsedControl"] svg,
    [data-testid="collapsedControl"] svg,
    section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] svg {
        fill: currentColor !important;
        color: currentColor !important;
    }

    /* ── Typography & Reset ── */
    html, body, p, h1, h2, h3, h4, h5, h6, label, .stMarkdown p, .stButton button, .stTextInput input, .stTextArea textarea {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Main Canvas Background ── */
    .stApp {
        background: radial-gradient(circle at 10% 8%, rgba(37, 99, 235, 0.08) 0%, transparent 40%),
                    radial-gradient(circle at 90% 90%, rgba(99, 102, 241, 0.06) 0%, transparent 40%),
                    #070A11 !important;
        color: #F1F5F9;
    }

    /* ── Top Header / Block Container Spacing ── */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1440px;
    }

    /* ── Card Containers ── */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #0C1220 !important;
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.35) !important;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(59, 130, 246, 0.35) !important;
        box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.45) !important;
    }

    /* ── Buttons Styling ── */
    .stButton>button {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 7px !important;
        font-weight: 600 !important;
        font-size: 12.5px !important;
        padding: 0.4rem 0.9rem !important;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25) !important;
        transition: all 0.15s ease !important;
        letter-spacing: 0.1px;
    }
    .stButton>button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4) !important;
        border-color: rgba(255, 255, 255, 0.25) !important;
    }
    .stButton>button:active {
        transform: translateY(0) !important;
    }

    /* ── Interactive KPI Metric Cards ── */
    div[class*="st-key-kpicard_"] {
        margin-bottom: 8px !important;
    }
    div[class*="st-key-kpicard_"] button {
        background: #0B101C !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 9px !important;
        padding: 10px 12px !important;
        height: auto !important;
        min-height: 72px !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: center !important;
        text-align: left !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        cursor: pointer !important;
    }
    div[class*="st-key-kpicard_"] button:hover {
        transform: translateY(-2px) !important;
        border-color: rgba(255, 255, 255, 0.22) !important;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4) !important;
    }
    div[class*="st-key-kpicard_por_candidatar"] button {
        border-top: 3.5px solid #EF4444 !important;
    }
    div[class*="st-key-kpicard_candidatado"] button {
        border-top: 3.5px solid #10B981 !important;
    }
    div[class*="st-key-kpicard_entrevista"] button {
        border-top: 3.5px solid #3B82F6 !important;
    }
    div[class*="st-key-kpicard_rejeitado"] button {
        border-top: 3.5px solid #64748B !important;
    }
    div[class*="st-key-kpicard_todas"] button {
        border-top: 3.5px solid #8B5CF6 !important;
    }

    div[class*="st-key-kpicard_por_candidatar"] button[kind="primary"],
    div[class*="st-key-kpicard_por_candidatar"] button[data-testid="baseButton-primary"] {
        background: rgba(239, 68, 68, 0.12) !important;
        border: 1.5px solid #EF4444 !important;
        border-top: 3.5px solid #EF4444 !important;
        box-shadow: 0 0 16px rgba(239, 68, 68, 0.25) !important;
    }
    div[class*="st-key-kpicard_candidatado"] button[kind="primary"],
    div[class*="st-key-kpicard_candidatado"] button[data-testid="baseButton-primary"] {
        background: rgba(16, 185, 129, 0.12) !important;
        border: 1.5px solid #10B981 !important;
        border-top: 3.5px solid #10B981 !important;
        box-shadow: 0 0 16px rgba(16, 185, 129, 0.25) !important;
    }
    div[class*="st-key-kpicard_entrevista"] button[kind="primary"],
    div[class*="st-key-kpicard_entrevista"] button[data-testid="baseButton-primary"] {
        background: rgba(59, 130, 246, 0.12) !important;
        border: 1.5px solid #3B82F6 !important;
        border-top: 3.5px solid #3B82F6 !important;
        box-shadow: 0 0 16px rgba(59, 130, 246, 0.25) !important;
    }
    div[class*="st-key-kpicard_rejeitado"] button[kind="primary"],
    div[class*="st-key-kpicard_rejeitado"] button[data-testid="baseButton-primary"] {
        background: rgba(100, 116, 139, 0.15) !important;
        border: 1.5px solid #94A3B8 !important;
        border-top: 3.5px solid #64748B !important;
        box-shadow: 0 0 16px rgba(100, 116, 139, 0.25) !important;
    }
    div[class*="st-key-kpicard_todas"] button[kind="primary"],
    div[class*="st-key-kpicard_todas"] button[data-testid="baseButton-primary"] {
        background: rgba(139, 92, 246, 0.12) !important;
        border: 1.5px solid #8B5CF6 !important;
        border-top: 3.5px solid #8B5CF6 !important;
        box-shadow: 0 0 16px rgba(139, 92, 246, 0.25) !important;
    }

    div[class*="st-key-kpicard_"] button div[data-testid="stMarkdownContainer"] {
        width: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: center !important;
        gap: 3px !important;
        text-align: left !important;
    }
    div[class*="st-key-kpicard_"] button div[data-testid="stMarkdownContainer"] p:first-child,
    div[class*="st-key-kpicard_"] button p:first-child {
        font-size: 10px !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px !important;
        color: #94A3B8 !important;
        text-transform: uppercase !important;
        margin: 0 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: block !important;
        width: 100% !important;
    }
    div[class*="st-key-kpicard_"] button div[data-testid="stMarkdownContainer"] p:last-child,
    div[class*="st-key-kpicard_"] button p:last-child {
        font-size: 24px !important;
        font-weight: 800 !important;
        color: #F8FAFC !important;
        letter-spacing: -0.5px !important;
        margin: 0 !important;
        line-height: 1.2 !important;
        display: block !important;
        width: 100% !important;
    }
    .stLinkButton>a {
        border-radius: 7px !important;
        font-weight: 600 !important;
        font-size: 12.5px !important;
        background: #1E293B !important;
        color: #E2E8F0 !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        padding: 0.4rem 0.9rem !important;
        transition: all 0.15s ease !important;
    }
    .stLinkButton>a:hover {
        background: #334155 !important;
        border-color: rgba(59, 130, 246, 0.4) !important;
        color: #FFFFFF !important;
    }

    /* ── Form Inputs & Selectboxes ── */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div {
        background: #0D131F !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        color: #F1F5F9 !important;
        font-size: 13px !important;
    }
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25) !important;
    }

    /* ── Streamlit Segmented Control (Executive Clean Tabs) ── */
    div[data-testid="stSegmentedControl"] {
        background: transparent !important;
        padding: 0 !important;
        border: none !important;
    }
    div[data-testid="stSegmentedControl"] > div {
        background: #090E18 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 8px !important;
        padding: 3px !important;
        gap: 3px !important;
    }
    div[data-testid="stSegmentedControl"] button {
        background: transparent !important;
        color: #94A3B8 !important;
        border: 1px solid transparent !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        transition: all 0.15s ease !important;
        padding: 6px 12px !important;
    }
    div[data-testid="stSegmentedControl"] button:hover {
        color: #F8FAFC !important;
        background: rgba(255, 255, 255, 0.04) !important;
    }
    div[data-testid="stSegmentedControl"] button[aria-checked="true"],
    div[data-testid="stSegmentedControl"] button[data-checked="true"],
    div[data-testid="stSegmentedControl"] button[aria-selected="true"] {
        background: #1E293B !important;
        color: #38BDF8 !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        box-shadow: 0 1px 6px rgba(0, 0, 0, 0.3) !important;
    }

    /* ── Streamlit Native Pills (Quick Filters) ── */
    div[data-testid="stPills"] {
        padding-top: 4px !important;
        padding-bottom: 2px !important;
    }
    div[data-testid="stPills"] button {
        background: rgba(15, 23, 42, 0.6) !important;
        color: #94A3B8 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 20px !important;
        font-size: 11.5px !important;
        font-weight: 600 !important;
        padding: 4px 12px !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stPills"] button:hover {
        background: rgba(30, 41, 59, 0.8) !important;
        color: #F1F5F9 !important;
        border-color: rgba(255, 255, 255, 0.15) !important;
    }
    div[data-testid="stPills"] button[aria-checked="true"],
    div[data-testid="stPills"] button[data-checked="true"],
    div[data-testid="stPills"] button[aria-selected="true"] {
        background: rgba(37, 99, 235, 0.2) !important;
        color: #60A5FA !important;
        border-color: rgba(59, 130, 246, 0.4) !important;
        box-shadow: 0 0 10px rgba(37, 99, 235, 0.2) !important;
    }

    /* ── Sidebar Redesign ── */
    section[data-testid="stSidebar"] {
        background-color: #06080F !important;
        border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        padding-bottom: 2px;
        padding-right: 32px;
    }
    .sidebar-brand-logo {
        width: 30px;
        height: 30px;
        border-radius: 7px;
        background: linear-gradient(135deg, #2563EB, #1E40AF);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        color: #FFFFFF;
        font-size: 12px;
        letter-spacing: -0.3px;
        border: 1px solid rgba(255, 255, 255, 0.15);
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
    }
    .sidebar-brand-text {
        font-size: 15px;
        font-weight: 700;
        letter-spacing: -0.3px;
        color: #F8FAFC;
    }
    .profile-card {
        background: #0B101C;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 9px;
        padding: 10px 12px;
        margin-top: 4px;
    }
    .profile-avatar {
        width: 32px;
        height: 32px;
        border-radius: 7px;
        background: #1E293B;
        border: 1px solid rgba(255, 255, 255, 0.1);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        color: #E2E8F0;
        font-size: 12px;
    }

    /* Sidebar Navigation Links */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label > div:first-child,
    section[data-testid="stSidebar"] div[data-testid="stRadio"] div[class*="RadioMark"],
    section[data-testid="stSidebar"] div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child,
    section[data-testid="stSidebar"] div[data-testid="stRadio"] input[type="radio"],
    section[data-testid="stSidebar"] div[data-testid="stRadio"] span[data-testid="stRadioPoint"] {
        display: none !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] {
        display: flex !important;
        flex-direction: column !important;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        gap: 3px !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] > label {
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        padding: 8px 12px !important;
        border-radius: 7px !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        color: #94A3B8 !important;
        background: transparent !important;
        border: 1px solid transparent !important;
        margin: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
        background: rgba(255, 255, 255, 0.04) !important;
        color: #F8FAFC !important;
        border-color: rgba(255, 255, 255, 0.06) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked),
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] > label[aria-checked="true"] {
        background: linear-gradient(90deg, rgba(37, 99, 235, 0.2) 0%, rgba(30, 41, 59, 0.3) 100%) !important;
        color: #60A5FA !important;
        border-left: 3px solid #3B82F6 !important;
        border-top: 1px solid rgba(59, 130, 246, 0.2) !important;
        border-right: 1px solid rgba(59, 130, 246, 0.1) !important;
        border-bottom: 1px solid rgba(59, 130, 246, 0.2) !important;
    }

    /* ── Expanders ── */
    div[data-testid="stExpander"] {
        background: #090E18 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 9px !important;
        overflow: hidden !important;
        margin-top: 6px !important;
        transition: border-color 0.2s ease !important;
    }
    div[data-testid="stExpander"]:hover {
        border-color: rgba(59, 130, 246, 0.25) !important;
    }
    div[data-testid="stExpander"] summary {
        color: #CBD5E1 !important;
        font-weight: 600 !important;
        font-size: 12.5px !important;
        padding: 8px 14px !important;
    }
    div[data-testid="stExpander"] summary:hover {
        color: #38BDF8 !important;
        background: rgba(255, 255, 255, 0.02) !important;
    }

    /* ── Clean Scrollbars ── */
    ::-webkit-scrollbar {
        width: 5px;
        height: 5px;
    }
    ::-webkit-scrollbar-track {
        background: #06080F;
    }
    ::-webkit-scrollbar-thumb {
        background: #1E293B;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #334155;
    }
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

