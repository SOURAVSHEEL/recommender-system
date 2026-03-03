
import streamlit as st

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

_LABEL_TO_CODE = {v: k for k, v in TEST_TYPE_LABELS.items()}


def inject_css():
    st.markdown("""
    <style>
        .card {
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 1.2rem 1.4rem;
            margin-bottom: 1rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        .card-name {
            font-size: 1.05rem;
            font-weight: 700;
            color: #1E3A5F;
            margin-bottom: 0.25rem;
        }
        .card-desc {
            font-size: 0.84rem;
            color: #475569;
            line-height: 1.6;
            margin-bottom: 0.5rem;
        }
        .card-url {
            display: block;
            font-family: monospace;
            font-size: 0.72rem;
            color: #64748B;
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 5px 10px;
            margin-bottom: 0.6rem;
            word-break: break-all;
        }
        .badge {
            display: inline-block;
            padding: 2px 9px;
            border-radius: 999px;
            font-size: 0.71rem;
            font-weight: 700;
            color: white;
            margin-right: 4px;
            margin-bottom: 2px;
        }
        .chip {
            display: inline-block;
            padding: 2px 9px;
            border-radius: 6px;
            font-size: 0.74rem;
            font-weight: 500;
            margin-right: 5px;
            background: #F1F5F9;
            color: #64748B;
        }
        .chip-on {
            background: #DCFCE7;
            color: #15803D;
        }
        .rank-num {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #1E3A5F;
            color: white;
            border-radius: 50%;
            width: 26px; height: 26px;
            font-size: 0.78rem;
            font-weight: 700;
            margin-right: 8px;
            flex-shrink: 0;
        }
        a.shl-link {
            font-size: 0.8rem;
            color: #2563EB;
            text-decoration: none;
            font-weight: 500;
        }
        a.shl-link:hover { text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)


def type_badge_html(code: str) -> str:
    color = TEST_TYPE_COLORS.get(code, "#94A3B8")
    label = TEST_TYPE_LABELS.get(code, code)
    return f'<span class="badge" style="background:{color}" title="{label}">{code}</span>'


def chip_html(label: str, active: bool = False) -> str:
    cls = "chip chip-on" if active else "chip"
    return f'<span class="{cls}">{label}</span>'


def result_card(rank: int, assessment: dict):
    """Render a single assessment result card."""
    name       = assessment.get("name", "")
    url        = assessment.get("url", "#")
    desc       = assessment.get("description", "")
    duration   = assessment.get("duration")
    remote     = assessment.get("remote_support", "No") == "Yes"
    adaptive   = assessment.get("adaptive_support", "No") == "Yes"
    test_types = assessment.get("test_type", [])

    # Resolve type codes from full labels or raw codes
    codes = []
    for t in test_types:
        code = _LABEL_TO_CODE.get(t) or (t if t in TEST_TYPE_COLORS else None)
        if code:
            codes.append(code)

    badges = "".join(type_badge_html(c) for c in codes)
    chips  = ""
    if duration:
        chips += chip_html(f"⏱ {duration} min")
    chips += chip_html("🌐 Remote", active=remote)
    chips += chip_html("⚡ Adaptive", active=adaptive)


    st.markdown(f"""
    <div class="card">
        <div style="display:flex;align-items:flex-start;gap:0.4rem;margin-bottom:0.4rem;">
            <span class="rank-num">{rank}</span>
            <div>
                <div class="card-name">{name}</div>
                <a class="shl-link" href="{url}" target="_blank">↗ View on SHL</a>
            </div>
        </div>
        <div class="card-desc">{desc}</div>
        <span class="card-url">&#x1F517; {url}</span>
        <div style="margin-bottom:0.4rem;">{badges}</div>
        <div>{chips}</div>
    </div>
    """, unsafe_allow_html=True)


# def legend():
#     """Render the test type legend as a grid."""
#     cols = st.columns(4)
#     for i, (code, label) in enumerate(TEST_TYPE_LABELS.items()):
#         color = TEST_TYPE_COLORS[code]
#         cols[i % 4].markdown(
#             f'<span class="badge" style="background:{color}">{code}</span> {label}',
#             unsafe_allow_html=True,
#         )


def sidebar_legend():
    """Render a clean legend panel in the sidebar explaining all badges and chips."""

    # ── Test Type Legend ──────────────────────────────────────────────────────
    st.sidebar.markdown(
        '''<div style="font-size:0.82rem;font-weight:700;color:#CBD5E1;
                       letter-spacing:0.04em;margin-bottom:0.6rem;">
            📋 TEST TYPES
        </div>''',
        unsafe_allow_html=True,
    )

    TEST_TYPE_DESC = {
        "A": "Cognitive ability: numerical, verbal, deductive & inductive reasoning",
        "B": "Scenario-based judgment tests & situational questionnaires",
        "C": "Structured behavioral competency frameworks (UCF)",
        "D": "360-degree feedback & leadership development reports",
        "E": "Group exercises, in-tray tasks & assessment centre tools",
        "K": "Job-specific technical knowledge: languages, tools & domains",
        "P": "Work style, personality traits, motivation & leadership potential",
        "S": "Realistic work simulations: coding, writing, data entry & more",
    }

    for code, label in TEST_TYPE_LABELS.items():
        color = TEST_TYPE_COLORS[code]
        desc  = TEST_TYPE_DESC[code]
        st.sidebar.markdown(
            f'''<div style="display:flex;align-items:flex-start;gap:8px;
                            margin-bottom:0.55rem;">
                <span style="display:inline-flex;align-items:center;justify-content:center;
                             background:{color};color:white;border-radius:50%;
                             width:22px;height:22px;font-size:0.7rem;font-weight:700;
                             flex-shrink:0;margin-top:1px;">{code}</span>
                <div>
                    <div style="font-size:0.78rem;font-weight:600;color:#E2E8F0;
                                line-height:1.2;">{label}</div>
                    <div style="font-size:0.71rem;color:#94A3B8;line-height:1.4;
                                margin-top:1px;">{desc}</div>
                </div>
            </div>''',
            unsafe_allow_html=True,
        )

    st.sidebar.markdown(
        '<hr style="border-color:#334155;margin:0.8rem 0;">',
        unsafe_allow_html=True,
    )

    # ── Result Card Badges Explained ─────────────────────────────────────────
    st.sidebar.markdown(
        '''<div style="font-size:0.82rem;font-weight:700;color:#CBD5E1;
                       letter-spacing:0.04em;margin-bottom:0.6rem;">
            🏷️ CARD INDICATORS
        </div>''',
        unsafe_allow_html=True,
    )

    indicators = [
        ("⏱", "#F1F5F9", "#334155",
         "Duration",
         "Approximate time to complete the assessment in minutes."),
        ("🌐", "#DCFCE7", "#15803D",
         "Remote",
         "Assessment can be taken online — no test centre required."),
        ("⚡", "#DCFCE7", "#15803D",
         "Adaptive",
         "Computer-adaptive: question difficulty adjusts to candidate responses for a shorter, more precise test."),
    ]

    for icon, bg, fg, title, explanation in indicators:
        st.sidebar.markdown(
            f'''<div style="display:flex;align-items:flex-start;gap:8px;
                            margin-bottom:0.55rem;">
                <span style="display:inline-flex;align-items:center;justify-content:center;
                             background:{bg};border-radius:6px;padding:2px 7px;
                             font-size:0.75rem;font-weight:600;color:{fg};
                             flex-shrink:0;white-space:nowrap;">{icon} {title}</span>
                <div style="font-size:0.71rem;color:#94A3B8;line-height:1.4;
                            margin-top:2px;">{explanation}</div>
            </div>''',
            unsafe_allow_html=True,
        )