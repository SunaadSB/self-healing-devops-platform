import os
import pandas as pd
import streamlit as st
from prometheus_api_client import PrometheusConnect
from streamlit_autorefresh import st_autorefresh


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Self-Healing DevOps Dashboard",
    page_icon="🤖",
    layout="wide"
)

st_autorefresh(
    interval=5000,
    key="dashboard_refresh"
)


# ============================================================
# PROMETHEUS CONNECTION
# ============================================================

PROMETHEUS_URL = "http://localhost:30090"

prom = PrometheusConnect(
    url=PROMETHEUS_URL,
    disable_ssl=True
)


# ============================================================
# HELPER FUNCTION
# ============================================================

def get_metric(query):
    try:
        result = prom.custom_query(query=query)

        if result:
            return float(result[0]["value"][1])

        return 0.0

    except Exception as e:
        st.warning(f"Query failed: {query}")
        return 0.0


# ============================================================
# LIVE METRICS
# ============================================================

cpu = get_metric(
    'rate(process_cpu_seconds_total[5m]) * 100'
)

memory = get_metric(
    'process_resident_memory_bytes'
)


# Request rates
user_rate = get_metric(
    'rate(user_requests_total[1m])'
)

order_rate = get_metric(
    'rate(order_requests_total[1m])'
)

payment_rate = get_metric(
    'rate(payment_requests_total[1m])'
)


# Request totals
user_total = get_metric(
    'user_requests_total'
)

order_total = get_metric(
    'order_requests_total'
)

payment_total = get_metric(
    'payment_requests_total'
)


# ============================================================
# TITLE
# ============================================================

st.title("🤖 AI Self-Healing DevOps Dashboard")

st.caption(
    "Kubernetes → Prometheus → AI Anomaly Detection → Self-Healing"
)

st.success("🟢 Connected to Prometheus")


# ============================================================
# SYSTEM METRICS
# ============================================================

st.header("📊 System Metrics")

col1, col2 = st.columns(2)

with col1:

    st.subheader("🖥️ CPU Usage")

    st.metric(
        "CPU",
        f"{cpu:.4f}%"
    )

    cpu_df = pd.DataFrame({
        "CPU (%)": [cpu]
    })

    st.bar_chart(
        cpu_df,
        height=250
    )


with col2:

    st.subheader("💾 Memory Usage")

    memory_mb = memory / 1024 / 1024

    st.metric(
        "Memory",
        f"{memory_mb:.2f} MB"
    )

    memory_df = pd.DataFrame({
        "Memory (MB)": [memory_mb]
    })

    st.bar_chart(
        memory_df,
        height=250
    )


# ============================================================
# USER SERVICE
# ============================================================

st.header("👤 User Service")

col1, col2 = st.columns(2)

with col1:

    st.metric(
        "Live Request Rate",
        f"{user_rate:.6f} req/s"
    )

with col2:

    st.metric(
        "Total Requests",
        f"{user_total:.0f}"
    )

user_df = pd.DataFrame({
    "User Requests/sec": [user_rate]
})

st.bar_chart(
    user_df,
    height=300
)


# ============================================================
# ORDER SERVICE
# ============================================================

st.header("📦 Order Service")

col1, col2 = st.columns(2)

with col1:

    st.metric(
        "Live Request Rate",
        f"{order_rate:.6f} req/s"
    )

with col2:

    st.metric(
        "Total Requests",
        f"{order_total:.0f}"
    )

order_df = pd.DataFrame({
    "Order Requests/sec": [order_rate]
})

st.bar_chart(
    order_df,
    height=300
)

st.info(
    f"📦 Order Service has processed "
    f"{order_total:.0f} total requests."
)


# ============================================================
# PAYMENT SERVICE
# ============================================================

st.header("💳 Payment Service")

col1, col2 = st.columns(2)

with col1:

    st.metric(
        "Live Request Rate",
        f"{payment_rate:.6f} req/s"
    )

with col2:

    st.metric(
        "Total Requests",
        f"{payment_total:.0f}"
    )

payment_df = pd.DataFrame({
    "Payment Requests/sec": [payment_rate]
})

st.bar_chart(
    payment_df,
    height=300
)


# ============================================================
# REQUEST SUMMARY
# ============================================================

st.header("📈 Request Summary")

summary = pd.DataFrame({
    "Service": [
        "User",
        "Order",
        "Payment"
    ],
    "Live Rate (req/s)": [
        user_rate,
        order_rate,
        payment_rate
    ],
    "Total Requests": [
        user_total,
        order_total,
        payment_total
    ]
})

st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# AI ANOMALY STATUS
# ============================================================

st.header("🤖 AI Anomaly Detection")

if os.path.exists("self_healing_log.csv"):

    logs = pd.read_csv(
        "self_healing_log.csv"
    )

    if not logs.empty:

        anomaly_events = logs[
            logs["event"] == "ANOMALY_DETECTED"
        ]

        recovery_events = logs[
            logs["event"] == "RECOVERY_SUCCESS"
        ]

        if len(recovery_events) > 0:

            st.success(
                "✅ Anomaly detected and successfully recovered"
            )

        elif len(anomaly_events) > 0:

            st.error(
                "🚨 Anomaly detected"
            )

        else:

            st.success(
                "✅ System operating normally"
            )

    else:

        st.success(
            "✅ System operating normally"
        )

else:

    st.success(
        "✅ System operating normally"
    )


# ============================================================
# SELF-HEALING STATUS
# ============================================================

st.header("🔄 Self-Healing Status")

if os.path.exists("self_healing_log.csv"):

    logs = pd.read_csv(
        "self_healing_log.csv"
    )

    if not logs.empty:

        latest = logs.iloc[-1]

        event = latest["event"]

        if event == "RECOVERY_SUCCESS":

            st.success(
                "✅ Self-healing completed successfully"
            )

        elif event == "ANOMALY_DETECTED":

            st.error(
                "🚨 Anomaly detected"
            )

        elif event == "SELF_HEALING_TRIGGERED":

            st.warning(
                "🔄 Self-healing action triggered"
            )

        elif event == "RECOVERY_FAILED":

            st.error(
                "❌ Recovery failed"
            )

        else:

            st.info(
                f"ℹ️ Latest event: {event}"
            )

    else:

        st.info(
            "No self-healing events recorded."
        )

else:

    st.info(
        "self_healing_log.csv not found."
    )


# ============================================================
# EVENT HISTORY
# ============================================================

st.header("📝 Self-Healing Event History")

if os.path.exists("self_healing_log.csv"):

    logs = pd.read_csv(
        "self_healing_log.csv"
    )

    if not logs.empty:

        st.dataframe(
            logs.tail(20),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No events recorded."
        )

else:

    st.info(
        "No event log available."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "🔄 Dashboard refreshes automatically every 5 seconds"
)