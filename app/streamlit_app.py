"""
streamlit_app.py — SHL Assessment Recommender UI

Run:
  streamlit run app/streamlit_app.py
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st
from app.components import inject_css, result_card, sidebar_legend

API_URL = "https://shl-recommender-system-ivjb.onrender.com"



# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SHL Assessment Recommender",
    page_icon="🎯",
    layout="wide",
)

inject_css()


# ── API helpers ───────────────────────────────────────────────────────────────

def ping_api() -> bool:
    """Return True if API is already up."""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=6)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def wake_api(status_placeholder) -> bool:
    """Wait for the API to wake up, updating status_placeholder each retry."""
    for attempt in range(1, 20):
        if ping_api():
            return True
        status_placeholder.info(
            f"⏳ Server is waking up... (attempt {attempt}/20). "
            f"This can take few mintues on first load. Please reload the page multiple times."
            f"Once the Backend server will run, UI screen will be invisible"
        )
        time.sleep(15)
    return False


def call_api(query: str, status_placeholder) -> list[dict] | None:
    status_placeholder.info("🔄 Sending request...")
    try:
        resp = requests.post(
            f"{API_URL}/recommend",
            json={"query": query},
            timeout=120,
        )
        resp.raise_for_status()
        status_placeholder.empty()
        return resp.json().get("recommended_assessments", [])
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Please try again.")
    except requests.exceptions.Timeout:
        st.error("Request timed out. The server may be busy — try again.")
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except (ValueError, AttributeError):
            detail = e.response.text if (e.response and e.response.text) else "Unknown API error"
        st.error(f"API error {e.response.status_code}: {detail}")
    except requests.exceptions.RequestException as e:
        st.error(f"Unexpected request error: {str(e)}")
    except (ValueError, KeyError) as e:
        st.error(f"Failed to parse API response: {str(e)}")
    return None


# ── Startup health check (runs once on page load) ─────────────────────────────

if "api_ready" not in st.session_state:
    st.session_state.api_ready = False

if not st.session_state.api_ready:
    startup_placeholder = st.empty()
    if ping_api():
        st.session_state.api_ready = True
    else:
        startup_placeholder.warning(
            "🌙 Server appears to be sleeping. Waking it up — "
            "this usually takes 30–40 seconds..."
        )
        if wake_api(startup_placeholder):
            st.session_state.api_ready = True
            startup_placeholder.success("🟢 Server is ready!")
            time.sleep(1)
            startup_placeholder.empty()
        else:
            startup_placeholder.error(
                "❌ Server did not respond after multiple retries. "
                "Please refresh the page."
            )
            st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.image("https://www.shl.com/assets/header-graphics/SHL-logo-colour-update.svg", width=120)
st.sidebar.markdown("---")
sidebar_legend()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## 🎯 SHL Assessment Recommender")
st.markdown("Enter a **job description**, **natural language query**, or paste a **URL** to a job posting.")

# ── Input ─────────────────────────────────────────────────────────────────────

query = st.text_area(
    label="query",
    placeholder=(
        "e.g. I need a Java developer who can collaborate with business teams\n\n"
        "or paste a full job description here..."
    ),
    height=150,
    label_visibility="collapsed",
)

col_btn, col_clear, _ = st.columns([1, 1, 6])
with col_btn:
    search = st.button("🔍  Search", use_container_width=True, type="primary")
with col_clear:
    clear = st.button("✕  Clear", use_container_width=True)

if clear:
    st.rerun()

st.markdown("---")

# ── Search & Results ──────────────────────────────────────────────────────────

if search:
    if not query.strip():
        st.warning("Please enter a query or URL.")
        st.stop()

    status_placeholder = st.empty()

    with st.spinner("Running hybrid search and reranking..."):
        assessments = call_api(query.strip(), status_placeholder)

    if assessments is None:
        st.stop()

    count = len(assessments)
    st.markdown(f"### {count} Assessment{'s' if count != 1 else ''} Found")

    for i, assessment in enumerate(assessments, 1):
        result_card(i, assessment)