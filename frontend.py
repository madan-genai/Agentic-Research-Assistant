import streamlit as st
import requests
import json

BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Agentic Research Assistant", layout="wide")

st.title("🔬 Agentic Research Assistant")

# ─────────────────────────────────────────────
# Sidebar — History
# ─────────────────────────────────────────────
st.sidebar.header("📜 Research History")

def load_history():
    try:
        res = requests.get(f"{BASE_URL}/history")
        if res.status_code == 200:
            return res.json()["reports"]
    except:
        return []
    return []

history = load_history()

selected_report_id = None

for item in history:
    if st.sidebar.button(f"{item['topic'][:40]}... ({item['id']})"):
        selected_report_id = item["id"]

# ─────────────────────────────────────────────
# Load selected report
# ─────────────────────────────────────────────
if selected_report_id:
    res = requests.get(f"{BASE_URL}/history/{selected_report_id}")
    if res.status_code == 200:
        report = res.json()

        st.subheader("📄 Report")
        st.markdown(report["report_md"])

        st.subheader("📚 Sources")
        for src in report["sources"]:
            st.write(f"- {src['title']}")
            if src.get("url"):
                st.write(src["url"])

        pdf_url = f"{BASE_URL}/history/{selected_report_id}/pdf"
        st.link_button("⬇ Download PDF", pdf_url)

    st.stop()

# ─────────────────────────────────────────────
# Research Input
# ─────────────────────────────────────────────
topic = st.text_input("Enter research topic")

col1, col2 = st.columns(2)

with col1:
    use_web = st.checkbox("Force Web Search")

with col2:
    start_btn = st.button("🚀 Start Research")

# ─────────────────────────────────────────────
# Streaming Output Containers
# ─────────────────────────────────────────────
status_box = st.empty()
thinking_box = st.container()
report_box = st.container()
summary_box = st.empty()

# ─────────────────────────────────────────────
# SSE Stream Reader
# ─────────────────────────────────────────────
def stream_research(topic, use_web):
    url = f"{BASE_URL}/research"

    payload = {
        "topic": topic,
        "web_search": use_web
    }

    with requests.post(url, json=payload, stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded = line.decode("utf-8")

                if decoded.startswith("data: "):
                    data = decoded.replace("data: ", "")

                    if data == "[DONE]":
                        break

                    yield json.loads(data)

# ─────────────────────────────────────────────
# Run Research
# ─────────────────────────────────────────────
if start_btn and topic:

    status_box.info("Starting research...")

    thinking_log = []

    for event in stream_research(topic, use_web):

        # ── Start ─────────────────────────────
        if event["event"] == "start":
            status_box.info(event["message"])

        # ── Node Start ────────────────────────
        elif event["event"] == "node_start":
            status_box.warning(f"⚙ {event['display']}")

        # ── Thinking Steps ────────────────────
        elif event["event"] == "thinking":
            thinking_log.append(event["message"])

            with thinking_box:
                st.subheader("🧠 Thinking Process")
                for step in thinking_log[-15:]:  # show last 15
                    st.write(step)

        # ── Complete ──────────────────────────
        elif event["event"] == "complete":
            status_box.success("✅ Research Complete")

            with report_box:
                st.subheader("📄 Final Report")
                st.markdown(event["report"])

                st.subheader("📚 Sources")
                for src in event["sources"]:
                    st.write(f"- {src['title']}")
                    if src.get("url"):
                        st.write(src["url"])

                pdf_url = f"{BASE_URL}/history/{event['report_id']}/pdf"
                st.link_button("⬇ Download PDF", pdf_url)

        # ── Summary ───────────────────────────
        elif event["event"] == "summary":
            summary = event["state"]

            summary_box.json(summary)

        # ── Error ─────────────────────────────
        elif event["event"] == "error":
            status_box.error(event["message"])
            