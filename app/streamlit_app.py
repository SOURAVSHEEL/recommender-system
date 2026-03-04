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

def wait_for_api(status_placeholder, retries: int = 10, delay: int = 5) -> bool:
    """Ping the URL repeatedly until it responds or retries are exhausted."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(f"{API_URL}/health", timeout=6)
            if resp.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass

        status_placeholder.info(
            f"Server is waking up... (attempt {attempt}/{retries}). "
            f"This can take 30–40 seconds on first load."
        )
        time.sleep(delay)

    return False


def get_available_api_url(status_placeholder) -> str | None:
    """Ping API; if sleeping, wait for it to wake up."""

    # ── Quick ping ────────────────────────────────────────────────────────────
    try:
        resp = requests.get(f"{API_URL}/health", timeout=6)
        if resp.status_code == 200:
            return API_URL
    except requests.exceptions.RequestException:
        pass

    # ── Not up yet — wait for it to wake ─────────────────────────────────────
    status_placeholder.warning(
        "Server appears to be sleeping. Waiting for it to wake up "
        "(this usually takes 30–40 seconds)..."
    )

    if wait_for_api(status_placeholder):
        return API_URL

    status_placeholder.error("Server did not respond after multiple retries.")
    return None


def call_api(query: str, status_placeholder) -> list[dict] | None:
    api_url = get_available_api_url(status_placeholder)

    if api_url is None:
        st.error("Server is unavailable. Please try again in a moment.")
        return None

    status_placeholder.success("Connected to API.")

    try:
        resp = requests.post(
            f"{api_url}/recommend",
            json={"query": query},
            timeout=120,
        )
        resp.raise_for_status()
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
        "or https://jobs.example.com/senior-data-analyst\n\n"
        "or paste a full job description here..."
    ),
    height=150,
    label_visibility="collapsed",
)

col_btn, col_clear, _ = st.columns([1, 1, 6])
with col_btn:
    search = st.button("Search", use_container_width=True, type="primary")
with col_clear:
    clear = st.button("Clear", use_container_width=True)

if clear:
    st.rerun()

st.markdown("---")

# ── Search & Results ──────────────────────────────────────────────────────────

if search:
    if not query.strip():
        st.warning("Please enter a query or URL.")
        st.stop()

    status_placeholder = st.empty()  # single slot for all API status messages

    with st.spinner("Running hybrid search and reranking..."):
        assessments = call_api(query.strip(), status_placeholder)

    if assessments is None:
        st.stop()

    count = len(assessments)
    st.markdown(f"### {count} Assessment{'s' if count != 1 else ''} Found")

    for i, assessment in enumerate(assessments, 1):
        result_card(i, assessment)