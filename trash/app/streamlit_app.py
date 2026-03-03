"""
streamlit_app.py
================
SHL Assessment Recommender — Streamlit UI

Run:
  streamlit run app/streamlit_app.py
"""

import requests
import streamlit as st

API_URL = "http://localhost:8000"

TEST_TYPE_COLORS = {
    "A": "#3B82F6",
    "B": "#8B5CF6",
    "C": "#10B981",
    "D": "#F59E0B",
    "E": "#EF4444",
    "K": "#0EA5E9",
    "P": "#EC4899",
    "S": "#14B8A6",
}

TEST_TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & SJT",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SHL Assessment Recommender",
    page_icon="🎯",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main { background-color: #F8FAFC; }
    .header-title {
        font-size: 2.2rem; font-weight: 700;
        color: #1E3A5F; margin-bottom: 0.2rem;
    }
    .header-sub {
        font-size: 1rem; color: #64748B; margin-bottom: 2rem;
    }
    .card {
        background: white; border: 1px solid #E2E8F0;
        border-radius: 12px; padding: 1.2rem 1.4rem;
        margin-bottom: 1rem; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .card-title { font-size: 1.05rem; font-weight: 600; color: #1E3A5F; margin-bottom: 0.4rem; }
    .card-desc  { font-size: 0.85rem; color: #475569; margin-bottom: 0.8rem; line-height: 1.5; }
    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 600; color: white;
        margin-right: 4px; margin-bottom: 4px;
    }
    .chip {
        display: inline-block; padding: 2px 10px; border-radius: 6px;
        font-size: 0.75rem; font-weight: 500; margin-right: 6px;
        background: #F1F5F9; color: #475569;
    }
    .chip-yes { background: #DCFCE7; color: #166534; }
    .rank-badge {
        display: inline-flex; align-items: center; justify-content: center;
        background: #1E3A5F; color: white; border-radius: 50%;
        width: 28px; height: 28px; font-size: 0.8rem; font-weight: 700;
        margin-right: 8px; flex-shrink: 0;
    }
    .divider { border-top: 1px solid #E2E8F0; margin: 1.5rem 0; }
    a.view-link { font-size: 0.82rem; color: #2563EB; text-decoration: none; font-weight: 500; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def type_badge(code):
    color = TEST_TYPE_COLORS.get(code, "#94A3B8")
    label = TEST_TYPE_LABELS.get(code, code)
    return f'<span class="badge" style="background:{color}" title="{label}">{code}</span>'


def chip(label, is_yes=False):
    cls = "chip chip-yes" if is_yes else "chip"
    return f'<span class="{cls}">{label}</span>'


def render_card(rank, assessment):
    name       = assessment.get("name", "")
    url        = assessment.get("url", "#")
    desc       = assessment.get("description", "")
    duration   = assessment.get("duration")
    remote     = assessment.get("remote_support", "No") == "Yes"
    adaptive   = assessment.get("adaptive_support", "No") == "Yes"
    test_types = assessment.get("test_type", [])

    label_to_code = {v: k for k, v in TEST_TYPE_LABELS.items()}
    codes = [label_to_code.get(t, t) for t in test_types if label_to_code.get(t, t) in TEST_TYPE_COLORS]

    badges = "".join(type_badge(c) for c in codes)
    chips  = ""
    if duration:
        chips += chip(f"⏱ {duration} min")
    chips += chip("🌐 Remote", is_yes=remote)
    chips += chip("⚡ Adaptive", is_yes=adaptive)

    short_desc = (desc[:180] + "…") if len(desc) > 180 else desc

    st.markdown(f"""
    <div class="card">
        <div style="display:flex;align-items:flex-start;gap:0.5rem;margin-bottom:0.5rem;">
            <span class="rank-badge">{rank}</span>
            <div>
                <div class="card-title">{name}</div>
                <a class="view-link" href="{url}" target="_blank">↗ View on SHL</a>
            </div>
        </div>
        <div class="card-desc">{short_desc}</div>
        <div style="margin-bottom:0.5rem;">{badges}</div>
        <div>{chips}</div>
    </div>
    """, unsafe_allow_html=True)


def call_api(query):
    try:
        resp = requests.post(
            f"{API_URL}/recommend",
            json={"query": query},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Make sure FastAPI is running on port 8000.")
    except requests.exceptions.Timeout:
        st.error("Request timed out. Try again.")
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
    return None


# ── Layout ────────────────────────────────────────────────────────────────────

st.markdown('<div class="header-title">🎯 SHL Assessment Recommender</div>', unsafe_allow_html=True)
st.markdown('<div class="header-sub">Enter a job description or natural language query to find the most relevant SHL assessments.</div>', unsafe_allow_html=True)

query = st.text_area(
    label="query",
    placeholder=(
        "e.g. I need a Java developer who can collaborate with business teams\n"
        "or paste a full job description here..."
    ),
    height=140,
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 5])
with col1:
    search = st.button("🔍 Find Assessments", use_container_width=True, type="primary")

with st.expander("ℹ️ Test Type Legend"):
    cols = st.columns(4)
    for i, (code, label) in enumerate(TEST_TYPE_LABELS.items()):
        cols[i % 4].markdown(
            f'<span class="badge" style="background:{TEST_TYPE_COLORS[code]}">{code}</span> {label}',
            unsafe_allow_html=True,
        )

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ── Results ───────────────────────────────────────────────────────────────────

if search:
    if not query.strip():
        st.warning("Please enter a query first.")
    else:
        with st.spinner("Retrieving and ranking assessments..."):
            result = call_api(query.strip())

        if result:
            assessments = result.get("recommended_assessments", [])
            st.markdown(f"### {len(assessments)} Assessments Found")
            for i, a in enumerate(assessments, 1):
                render_card(i, a)