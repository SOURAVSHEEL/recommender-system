import streamlit as st

# ─────────────────────────────────────────────────────────────
# Test Type Color Mapping
# ─────────────────────────────────────────────────────────────

TEST_TYPE_COLORS = {
    "Knowledge & Skills": "#1f77b4",
    "Personality & Behavior": "#ff7f0e",
    "Ability & Aptitude": "#2ca02c",
    "Biodata & Situational": "#9467bd",
    "Assessment Center": "#8c564b",
}


# ─────────────────────────────────────────────────────────────
# Badge Component
# ─────────────────────────────────────────────────────────────

def badge(label: str, color: str = "#444"):
    st.markdown(
        f"""
        <span style="
            background-color:{color};
            color:white;
            padding:4px 10px;
            border-radius:12px;
            font-size:12px;
            margin-right:6px;">
            {label}
        </span>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Result Card Component
# ─────────────────────────────────────────────────────────────

def result_card(result: dict):
    with st.container():
        st.markdown("### " + result["name"])

        # Test Type Badges
        for t in result.get("test_type", []):
            color = TEST_TYPE_COLORS.get(t, "#555")
            badge(t, color)

        st.markdown("")

        # Description
        st.write(result["description"])

        col1, col2, col3 = st.columns(3)

        with col1:
            badge(f"⏱ {result.get('duration', 'N/A')} mins", "#333")

        with col2:
            badge(f"🌐 Remote: {result.get('remote_support')}", "#0a9396")

        with col3:
            badge(f"⚡ Adaptive: {result.get('adaptive_support')}", "#ae2012")

        st.markdown(
            f"[🔗 View Assessment]({result['url']})",
        )

        st.divider()