from pathlib import Path
import sqlite3
import sys

import pandas as pd
import streamlit as st


# ============================================================
# 1. Project imports and configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.dashboard_service import (
    find_delayed_shipments,
    find_exception_shipments,
    find_asset_exceptions,
)
from src.services.assistant_service import answer_question
from src.services.assistant_context_service import build_operational_context


DEFAULT_DB = (
    PROJECT_ROOT
    / "data"
    / "generated"
    / "custody_consistent_100k.db"
)

st.set_page_config(
    page_title="Reverse Logistics Control Tower",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 2. Professional light theme
# ============================================================

st.markdown(
    """
    <style>
    :root {
        --rl-navy: #17324d;
        --rl-blue: #2563eb;
        --rl-teal: #0f766e;
        --rl-ink: #172b4d;
        --rl-muted: #64748b;
        --rl-line: #e2e8f0;
        --rl-panel: #ffffff;
        --rl-canvas: #f5f8fc;
    }
    .stApp { background: var(--rl-canvas); color: var(--rl-ink); }
    [data-testid="stHeader"] { background: rgba(245, 248, 252, 0.92); }
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid var(--rl-line);
    }
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: var(--rl-navy); }
    .block-container { padding-top: 1.6rem; padding-bottom: 2rem; }
    .rl-hero {
        background: linear-gradient(115deg, #17324d 0%, #24577a 62%, #0f766e 100%);
        padding: 1.5rem 1.7rem;
        border-radius: 18px;
        color: #ffffff;
        margin-bottom: 1.1rem;
        box-shadow: 0 8px 24px rgba(23, 50, 77, 0.12);
    }
    .rl-eyebrow {
        text-transform: uppercase; letter-spacing: .13em;
        font-size: .72rem; font-weight: 700; opacity: .82;
    }
    .rl-hero h1 { color: #ffffff; margin: .35rem 0 .45rem 0; font-size: 2rem; }
    .rl-hero p { color: #e7f0f7; margin: 0; font-size: .98rem; }
    .rl-section-note { color: var(--rl-muted); margin-top: -.45rem; font-size: .9rem; }
    [data-testid="stMetric"] {
        background: var(--rl-panel);
        border: 1px solid var(--rl-line);
        padding: 1rem 1.05rem;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, .025);
    }
    [data-testid="stMetricLabel"] { color: var(--rl-muted); }
    [data-testid="stMetricValue"] { color: var(--rl-navy); }
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--rl-line);
        border-radius: 12px;
        overflow: hidden;
    }
    .rl-status {
        display: inline-block; padding: .25rem .55rem; border-radius: 999px;
        background: #eaf2ff; color: #1d4ed8; font-size: .78rem; font-weight: 650;
    }
    div.stButton > button {
        border-radius: 10px; font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 3. Read-only database access
# ============================================================

@st.cache_data(ttl=10, show_spinner=False)
def load_query(db_path: str, query: str, params: tuple = ()) -> pd.DataFrame:
    """Execute a parameterized query against SQLite in read-only mode."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return pd.read_sql_query(query, connection, params=params)


def safe_total(frame: pd.DataFrame, column: str = "total") -> int:
    """Return a safe integer total for a DataFrame column."""
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].fillna(0).sum())


def show_table(frame: pd.DataFrame, empty_message: str) -> None:
    if frame.empty:
        st.info(empty_message)
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True)


if not DEFAULT_DB.exists():
    st.error("Database not found: {}".format(DEFAULT_DB))
    st.info(
        "Generate the dataset first, or update DEFAULT_DB to point to "
        "your existing generated database."
    )
    st.stop()


# ============================================================
# 4. Load source data
# ============================================================

try:
    assets = load_query(
        str(DEFAULT_DB),
        """
        SELECT asset_status, condition_status, COUNT(*) AS total
        FROM reusable_assets
        GROUP BY asset_status, condition_status
        ORDER BY total DESC
        """,
    )

    asset_details = load_query(
        str(DEFAULT_DB),
        """
        SELECT
            a.asset_id,
            t.type_name AS asset_type,
            a.asset_status,
            a.condition_status,
            l.location_name AS current_location,
            o.owner_name AS owner
        FROM reusable_assets a
        JOIN asset_types t ON t.asset_type_id = a.asset_type_id
        JOIN owners o ON o.owner_id = a.owner_id
        LEFT JOIN locations l ON l.location_id = a.current_location_id
        ORDER BY a.asset_id
        """,
    )

    shipments = load_query(
        str(DEFAULT_DB),
        """
        SELECT shipment_status, COUNT(*) AS total
        FROM shipments
        GROUP BY shipment_status
        ORDER BY total DESC
        """,
    )

    returns = load_query(
        str(DEFAULT_DB),
        """
        SELECT return_status, COUNT(*) AS total
        FROM return_authorizations
        GROUP BY return_status
        ORDER BY total DESC
        """,
    )

    repairs = load_query(
        str(DEFAULT_DB),
        """
        SELECT repair_status, COUNT(*) AS total,
               COALESCE(SUM(repair_cost), 0) AS repair_cost
        FROM repairs
        GROUP BY repair_status
        ORDER BY total DESC
        """,
    )

    inspections = load_query(
        str(DEFAULT_DB),
        """
        SELECT inspection_status, COUNT(*) AS total
        FROM inspections
        GROUP BY inspection_status
        ORDER BY total DESC
        """,
    )

    shipment_details = load_query(
        str(DEFAULT_DB),
        """
        SELECT
            s.shipment_id,
            s.shipment_status,
            origin.location_name AS origin,
            destination.location_name AS destination,
            s.dispatched_at,
            s.delivered_at,
            ROUND(julianday('now') - julianday(s.dispatched_at), 1)
                AS days_since_dispatch
        FROM shipments s
        JOIN locations origin ON origin.location_id = s.origin_location_id
        JOIN locations destination
            ON destination.location_id = s.destination_location_id
        ORDER BY s.created_at DESC, s.shipment_id
        """,
    )

    missing_actor_events = load_query(
        str(DEFAULT_DB),
        """
        SELECT c.custody_event_id, c.asset_id, c.shipment_id, c.event_type,
               c.occurred_at, c.from_location_id, c.to_location_id
        FROM custody_events c
        WHERE c.actor_id IS NULL
        ORDER BY c.occurred_at DESC
        """,
    )

    conflicting_custody = load_query(
        str(DEFAULT_DB),
        """
        SELECT asset_id, occurred_at, COUNT(*) AS event_count,
               COUNT(DISTINCT to_location_id) AS destination_count
        FROM custody_events
        GROUP BY asset_id, occurred_at
        HAVING COUNT(DISTINCT to_location_id) > 1
        ORDER BY occurred_at DESC
        """,
    )

except (sqlite3.Error, pd.errors.DatabaseError) as error:
    st.error("Unable to load dashboard data: {}".format(error))
    st.stop()


# ============================================================
# 5. Header
# ============================================================

st.markdown(
    """
    <div class="rl-hero">
      <div class="rl-eyebrow">Operations intelligence · Reverse logistics</div>
      <h1>Reverse Logistics Control Tower</h1>
      <p>Track reusable assets, monitor movement, investigate exceptions,
      and make operational decisions from one workspace.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

header_left, header_right = st.columns([4, 1])
with header_left:
    st.caption("Source database: {} · Read-only connection".format(DEFAULT_DB.name))
with header_right:
    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# 6. Sidebar filters
# ============================================================

st.sidebar.markdown("## Control tower")
st.sidebar.caption("Filter the operational views below.")
st.sidebar.divider()

shipment_statuses = sorted(
    shipment_details["shipment_status"].dropna().unique().tolist()
)
selected_shipment_statuses = st.sidebar.multiselect(
    "Shipment status",
    options=shipment_statuses,
    default=shipment_statuses,
)

delay_days = st.sidebar.slider(
    "Potential delay threshold (days)",
    min_value=1,
    max_value=30,
    value=3,
    help="A shipment is flagged when its status is Dispatched or In Transit "
         "and its rounded dispatch age is greater than this threshold.",
)

return_statuses = sorted(returns["return_status"].dropna().unique().tolist())
selected_return_statuses = st.sidebar.multiselect(
    "Return status", options=return_statuses, default=return_statuses
)

repair_statuses = sorted(repairs["repair_status"].dropna().unique().tolist())
selected_repair_statuses = st.sidebar.multiselect(
    "Repair status", options=repair_statuses, default=repair_statuses
)

st.sidebar.divider()
st.sidebar.caption(
    "AI answers use local Ollama/Qwen and retrieved local rule documents. "
    "No external API key is required."
)


# ============================================================
# 7. Filtered calculations and KPI row
# ============================================================

filtered_shipments = shipment_details[
    shipment_details["shipment_status"].isin(selected_shipment_statuses)
].copy()

delayed_shipments = find_delayed_shipments(filtered_shipments, delay_days)
exception_shipments = find_exception_shipments(filtered_shipments)
asset_exceptions = find_asset_exceptions(asset_details)

filtered_returns = returns[
    returns["return_status"].isin(selected_return_statuses)
].copy()
filtered_repairs = repairs[
    repairs["repair_status"].isin(selected_repair_statuses)
].copy()

total_assets = safe_total(assets)
total_shipments = safe_total(shipments)
total_returns = safe_total(returns)
open_repairs = (
    int(
        repairs.loc[
            repairs["repair_status"].isin(["Open", "In Progress"]), "total"
        ].sum()
    )
    if not repairs.empty else 0
)
repair_cost = float(repairs["repair_cost"].sum()) if not repairs.empty else 0.0

st.subheader("Operational pulse")
st.markdown(
    '<div class="rl-section-note">Live summary from the local operational database.</div>',
    unsafe_allow_html=True,
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Reusable assets", "{:,}".format(total_assets))
k2.metric("Total shipments", "{:,}".format(total_shipments))
k3.metric("Return authorizations", "{:,}".format(total_returns))
k4.metric("Open repairs", "{:,}".format(open_repairs))
k5.metric("Potential delays", "{:,}".format(len(delayed_shipments)))

st.divider()


# ============================================================
# 8. Main workspace tabs
# ============================================================

overview_tab, exceptions_tab, investigate_tab, assistant_tab = st.tabs(
    [
        "📊 Overview",
        "🚨 Exceptions",
        "🔎 Shipment investigation",
        "🤖 AI assistant",
    ]
)


# ------------------------------------------------------------
# Overview tab
# ------------------------------------------------------------

with overview_tab:
    st.subheader("Network overview")
    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown("**Asset status and condition**")
        if assets.empty:
            st.info("No asset records found.")
        else:
            asset_status = (
                assets.groupby("asset_status", as_index=False)["total"]
                .sum()
                .sort_values("total", ascending=False)
            )
            st.bar_chart(asset_status, x="asset_status", y="total")
            with st.expander("View asset status details"):
                show_table(assets, "No asset status data.")

    with chart_right:
        st.markdown("**Shipment status**")
        if shipments.empty:
            st.info("No shipment records found.")
        else:
            st.bar_chart(shipments, x="shipment_status", y="total")
            with st.expander("View shipment status details"):
                show_table(shipments, "No shipment status data.")

    st.divider()
    st.subheader("Returns and repairs")
    return_col, repair_col = st.columns(2)

    with return_col:
        st.markdown("**Return authorization status**")
        if returns.empty:
            st.info("No return authorizations found.")
        else:
            st.bar_chart(returns, x="return_status", y="total")
            show_table(
                filtered_returns,
                "No return records match the selected filter.",
            )

    with repair_col:
        st.markdown("**Repair workload**")
        st.metric("Total recorded repair cost", "₹{:,.2f}".format(repair_cost))
        if not filtered_repairs.empty:
            st.bar_chart(filtered_repairs, x="repair_status", y="total")
        show_table(
            filtered_repairs,
            "No repair records match the selected filter.",
        )

    st.divider()
    st.subheader("Inspection outcomes")
    if inspections.empty:
        st.info("No inspection records found.")
    else:
        inspection_left, inspection_right = st.columns([1, 2])
        with inspection_left:
            st.bar_chart(inspections, x="inspection_status", y="total")
        with inspection_right:
            show_table(inspections, "No inspection data.")


# ------------------------------------------------------------
# Exceptions tab
# ------------------------------------------------------------

with exceptions_tab:
    st.subheader("Exception monitoring")
    st.caption(
        "Use these queues to identify records that may need operational review. "
        "Potential delay is an age-based indicator, not proof of a missed commitment."
    )

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Exception shipments", len(exception_shipments))
    e2.metric("Potentially delayed", len(delayed_shipments))
    e3.metric("Lost / damaged assets", len(asset_exceptions))
    e4.metric("Missing custody actor", len(missing_actor_events))

    with st.expander("Exception-status shipments", expanded=True):
        show_table(
            exception_shipments,
            "No exception-status shipments match the current shipment filter.",
        )

    with st.expander(
        "Potentially delayed shipments — over {} days".format(delay_days),
        expanded=True,
    ):
        show_table(
            delayed_shipments,
            "No shipments meet the selected status and age threshold.",
        )

    with st.expander("Lost or damaged assets"):
        show_table(asset_exceptions, "No lost or damaged assets were found.")

    with st.expander("Custody events missing an actor"):
        show_table(
            missing_actor_events,
            "All returned custody events have an assigned actor.",
        )

    with st.expander("Potentially conflicting custody destinations"):
        show_table(
            conflicting_custody,
            "No conflicting destinations at identical asset timestamps were found.",
        )

    st.divider()
    st.subheader("Action queue guidance")
    st.markdown(
        "- Confirm the latest carrier or warehouse status before treating a potential delay as a service failure.\n"
        "- Review failed inspections before returning an asset to service.\n"
        "- Resolve missing custody actors so that responsibility is traceable.\n"
        "- Investigate conflicting destination records before changing an asset's location."
    )


# ------------------------------------------------------------
# Shipment investigation tab
# ------------------------------------------------------------

with investigate_tab:
    st.subheader("Shipment investigation")
    st.caption(
        "Choose a shipment to inspect its route, timestamps, linked assets, "
        "and custody history."
    )

    if shipment_details.empty:
        st.info("No shipments are available to investigate.")
    else:
        shipment_labels = {
            row["shipment_id"]: "{} — {}".format(
                row["shipment_id"], row["shipment_status"]
            )
            for _, row in shipment_details.iterrows()
        }

        selected_shipment_id = st.selectbox(
            "Select a shipment",
            options=shipment_details["shipment_id"].tolist(),
            format_func=lambda shipment_id: shipment_labels[shipment_id],
            key="investigation_shipment_id",
        )

        selected_shipment = shipment_details[
            shipment_details["shipment_id"] == selected_shipment_id
        ].iloc[0]

        st.markdown("### Shipment {}".format(selected_shipment_id))
        s1, s2, s3 = st.columns(3)
        s1.metric("Status", str(selected_shipment["shipment_status"]))
        s2.metric("Origin", str(selected_shipment["origin"]))
        s3.metric("Destination", str(selected_shipment["destination"]))

        time_left, time_right = st.columns(2)
        with time_left:
            st.markdown("**Dispatched**")
            st.write(
                str(selected_shipment["dispatched_at"])
                if pd.notna(selected_shipment["dispatched_at"])
                else "Not recorded"
            )
        with time_right:
            st.markdown("**Delivered**")
            st.write(
                str(selected_shipment["delivered_at"])
                if pd.notna(selected_shipment["delivered_at"])
                else "Not recorded"
            )

        days_since = selected_shipment["days_since_dispatch"]
        if (
            selected_shipment["shipment_status"] in ["Dispatched", "In Transit"]
            and pd.notna(days_since)
            and float(days_since) > delay_days
        ):
            st.warning(
                "Potential delay: dispatch age is {} days, above the selected "
                "{}-day threshold. Verify the delivery commitment and latest status."
                .format(days_since, delay_days)
            )

        linked_assets = load_query(
            str(DEFAULT_DB),
            """
            SELECT sa.asset_id, t.type_name AS asset_type, sa.quantity,
                   a.asset_status, a.condition_status, sa.loaded_at, sa.unloaded_at
            FROM shipment_assets sa
            JOIN reusable_assets a ON a.asset_id = sa.asset_id
            JOIN asset_types t ON t.asset_type_id = a.asset_type_id
            WHERE sa.shipment_id = ?
            ORDER BY sa.asset_id
            """,
            (selected_shipment_id,),
        )

        st.markdown("### Associated assets")
        show_table(linked_assets, "No assets are linked to this shipment.")

        custody_history = load_query(
            str(DEFAULT_DB),
            """
            SELECT c.custody_event_id, c.asset_id, c.shipment_id, c.event_type,
                   c.occurred_at, actor.actor_name AS actor,
                   source.location_name AS from_location,
                   destination.location_name AS to_location, c.notes
            FROM custody_events c
            LEFT JOIN actors actor ON actor.actor_id = c.actor_id
            LEFT JOIN locations source ON source.location_id = c.from_location_id
            LEFT JOIN locations destination
                ON destination.location_id = c.to_location_id
            WHERE c.shipment_id = ?
               OR c.asset_id IN (
                    SELECT asset_id FROM shipment_assets WHERE shipment_id = ?
               )
            ORDER BY c.occurred_at, c.custody_event_id
            """,
            (selected_shipment_id, selected_shipment_id),
        )

        st.markdown("### Custody and event history")
        show_table(
            custody_history,
            "No custody events were found for this shipment or its assets.",
        )


# ------------------------------------------------------------
# Local AI assistant tab
# ------------------------------------------------------------

with assistant_tab:
    st.subheader("Reverse Logistics AI Assistant")
    st.caption(
        "Local Qwen via Ollama, with retrieved logistics rules and current "
        "read-only operational context. Verify consequential decisions against source records."
    )

    suggested_questions = [
        "Which shipments may be delayed?",
        "Summarize current return and repair workload.",
        "What operational exceptions should be reviewed first?",
        "Explain the rule for identifying a potentially delayed shipment.",
        "What custody data-quality issues are present?",
    ]

    st.markdown("**Try a question**")
    suggestion_cols = st.columns(2)
    for index, suggestion in enumerate(suggested_questions):
        with suggestion_cols[index % 2]:
            if st.button(
                suggestion,
                key="suggested_question_{}".format(index),
                use_container_width=True,
            ):
                st.session_state["pending_assistant_question"] = suggestion

    if "assistant_messages" not in st.session_state:
        st.session_state["assistant_messages"] = []

    for message in st.session_state["assistant_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    pending_question = st.session_state.pop(
        "pending_assistant_question", None
    )
    typed_question = st.chat_input(
        "Ask about assets, shipments, returns, repairs, or custody..."
    )
    question = typed_question or pending_question

    if question:
        st.session_state["assistant_messages"].append(
            {"role": "user", "content": question}
        )
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner(
                "Reading operational data and consulting local Qwen..."
            ):
                try:
                    operational_context = build_operational_context(DEFAULT_DB)
                    response = answer_question(question, operational_context)
                except Exception as error:
                    response = (
                        "I couldn't complete the request. Please verify that "
                        "Ollama is running, the local models are available, and "
                        "the database is accessible.\n\n"
                        "Technical detail: {}".format(error)
                    )
            st.markdown(response)

        st.session_state["assistant_messages"].append(
            {"role": "assistant", "content": response}
        )
        st.rerun()

    if st.session_state["assistant_messages"]:
        if st.button("Clear this chat", key="clear_assistant_chat"):
            st.session_state["assistant_messages"] = []
            st.rerun()


# ============================================================
# 9. Footer and limitations
# ============================================================

st.divider()
footer_left, footer_right = st.columns([3, 2])
with footer_left:
    st.caption(
        "Source: {} · SQLite read-only mode · Dashboard query cache: 10 seconds."
        .format(DEFAULT_DB.name)
    )
with footer_right:
    st.caption(
        "Potential delay is not proof of a missed delivery commitment. "
        "AI responses are advisory and should be verified."
    )
