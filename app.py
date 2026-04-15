import os
import json
import re
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient

# Load API keys
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

HISTORY_FILE = "history.json"

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Research Agent",
    page_icon="🔍",
    layout="wide"
)

# ─────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0f1117; }
    h1 { font-size: 2.2rem !important; font-weight: 700 !important; color: #ffffff !important; }
    [data-testid="metric-container"] {
        background: #1e2130;
        border: 1px solid #2e3250;
        border-radius: 12px;
        padding: 1rem;
    }
    .stButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        border: none !important;
        color: white !important;
        padding: 0.6rem 2rem !important;
        font-size: 1rem !important;
    }
    .stTextInput > div > div > input {
        background: #1e2130 !important;
        border: 1px solid #2e3250 !important;
        border-radius: 10px !important;
        color: #ffffff !important;
        font-size: 1rem !important;
        padding: 0.75rem 1rem !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 2px rgba(99,102,241,0.3) !important;
    }
    [data-testid="stSidebar"] {
        background-color: #13151f !important;
        border-right: 1px solid #2e3250 !important;
    }
    .streamlit-expanderHeader {
        background: #1e2130 !important;
        border-radius: 8px !important;
        color: #c9d1d9 !important;
    }
    hr { border-color: #2e3250 !important; }
    div[data-testid="column"] .stButton > button {
        background: #1e2130 !important;
        border: 1px solid #2e3250 !important;
        color: #a0aec0 !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        border-radius: 20px !important;
        padding: 0.4rem 0.8rem !important;
    }
    div[data-testid="column"] .stButton > button:hover {
        border-color: #6366f1 !important;
        color: #6366f1 !important;
        background: #1a1d2e !important;
    }
    .source-item {
        background: #1e2130;
        border: 1px solid #2e3250;
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-green {
        background: #0d3320;
        color: #3ecf8e;
        border: 1px solid #1a6640;
    }
    .search-item {
        font-family: monospace;
        font-size: 0.85rem;
        color: #6366f1;
        padding: 0.3rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# History helpers
# ─────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_to_history(topic, report, sources):
    history = load_history()
    history.insert(0, {
        "topic": topic,
        "report": report,
        "sources": sources,
        "date": datetime.now().strftime("%B %d, %Y — %H:%M")
    })
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

# ─────────────────────────────────────────────
# Web search
# ─────────────────────────────────────────────
def web_search(query, sources):
    try:
        results = tavily.search(query=query, max_results=3, include_answer=True)
        for r in results.get("results", []):
            if r["url"] not in [s["url"] for s in sources]:
                sources.append({"url": r["url"], "title": r.get("title", r["url"])})
        output = ""
        if results.get("answer"):
            output += f"Quick answer: {results['answer']}\n\n"
        for i, r in enumerate(results.get("results", []), 1):
            output += f"[{i}] {r['title']}\nURL: {r['url']}\n{r['content']}\n\n"
        return output
    except Exception as e:
        return f"Search failed: {str(e)}"

# ─────────────────────────────────────────────
# Step 1: Get search queries
# ─────────────────────────────────────────────
def get_search_queries(topic):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": "You are a research planner. Given a topic, return exactly 5 search queries as a JSON array of strings. Return ONLY the JSON array, nothing else. Example: [\"query 1\", \"query 2\", \"query 3\", \"query 4\", \"query 5\"]"
            },
            {
                "role": "user",
                "content": f"Topic: {topic}\n\nGive me 5 specific search queries about '{topic}'. Each query must be directly about {topic}."
            }
        ]
    )
    text = response.choices[0].message.content.strip()
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return [topic]

# ─────────────────────────────────────────────
# Step 2: Write report
# ─────────────────────────────────────────────
def write_report(topic, search_results):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2048,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert research writer. "
                    "Using the search results provided, write a comprehensive, well-structured report in markdown. "
                    "Include clear sections with headers, key findings, analysis, and a conclusion. "
                    "Be thorough and detailed."
                )
            },
            {
                "role": "user",
                "content": f"Topic: {topic}\n\nSearch Results:\n{search_results}\n\nWrite a full research report about {topic}."
            }
        ]
    )
    return response.choices[0].message.content

# ─────────────────────────────────────────────
# Main research function
# ─────────────────────────────────────────────
def research(topic, status_box, search_box, progress_bar):
    sources = []
    all_results = ""

    status_box.info("🧠 Planning research queries...")
    queries = get_search_queries(topic)

    for i, query in enumerate(queries):
        status_box.info(f"🔍 Searching: **{query}**")
        search_box.markdown(f'<div class="search-item">🔍 {query}</div>', unsafe_allow_html=True)
        result = web_search(query, sources)
        all_results += f"--- Search: {query} ---\n{result}\n\n"
        progress_bar.progress((i + 1) / (len(queries) + 1))

    status_box.info("✍️ Writing report...")
    report = write_report(topic, all_results)
    progress_bar.progress(1.0)

    return report, sources

# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📊 Session stats")
    if "total_reports" not in st.session_state:
        st.session_state.total_reports = 0
    if "total_searches" not in st.session_state:
        st.session_state.total_searches = 0

    col1, col2 = st.columns(2)
    col1.metric("Reports", st.session_state.total_reports)
    col2.metric("Searches", st.session_state.total_searches)

    st.divider()
    st.markdown('<span class="status-badge badge-green">● Groq connected</span>', unsafe_allow_html=True)
    st.markdown("")
    st.markdown('<span class="status-badge badge-green">● Tavily connected</span>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🕓 History")
    history = load_history()

    if not history:
        st.caption("No reports yet.")
    else:
        for i, item in enumerate(history):
            with st.expander(f"📄 {item['topic'][:28]}..."):
                st.caption(item["date"])
                if st.button("Load report", key=f"load_{i}", use_container_width=True):
                    st.session_state.loaded_report = item

    if history:
        st.divider()
        if st.button("🗑️ Clear history", use_container_width=True):
            os.remove(HISTORY_FILE)
            st.rerun()

# ─────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────
st.markdown("# 🔍 Research Agent")
st.caption("Powered by Groq + Tavily — free, fast, and private")
st.divider()

# Show loaded report from history
if "loaded_report" in st.session_state:
    item = st.session_state.loaded_report
    st.info(f"📄 Viewing: **{item['topic']}** — {item['date']}")
    st.markdown(item["report"])

    st.divider()
    st.subheader("🔗 Sources")
    for i, s in enumerate(item["sources"], 1):
        st.markdown(f'<div class="source-item">{i}. <a href="{s["url"]}" target="_blank">{s["title"]}</a></div>', unsafe_allow_html=True)

    st.divider()
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← Back"):
            del st.session_state.loaded_report
            st.rerun()
    with col2:
        st.download_button(
            label="⬇️ Download as .md",
            data=item["report"],
            file_name=f"report_{item['topic'][:30].replace(' ', '_')}.md",
            mime="text/markdown"
        )

else:
    if "run_topic" not in st.session_state:
        st.session_state.run_topic = None

    topic = st.text_input(
        "",
        placeholder="Enter a research topic — e.g. The future of AI in healthcare",
        label_visibility="collapsed"
    )

    st.caption("Quick picks — click to run instantly:")
    cols = st.columns(4)
    suggestions = ["AI in Africa", "Crypto markets 2026", "Climate change solutions", "Space exploration 2026"]
    for i, s in enumerate(suggestions):
        if cols[i].button(s, use_container_width=True):
            st.session_state.run_topic = s
            st.rerun()

    active_topic = st.session_state.run_topic or topic

    st.markdown("")

    if st.session_state.run_topic or st.button("🚀 Run Research Agent", type="primary", disabled=not topic):
        st.session_state.run_topic = None
        st.divider()
        st.markdown(f"### Researching: *{active_topic}*")

        status_box = st.empty()
        progress_bar = st.progress(0)
        st.markdown("**Live searches:**")
        search_box = st.container()

        with st.spinner("Agent is working..."):
            report, sources = research(active_topic, status_box, search_box, progress_bar)

        save_to_history(active_topic, report, sources)
        st.session_state.total_reports += 1
        st.session_state.total_searches += len(sources)

        status_box.success("✅ Research complete!")

        st.divider()
        st.subheader("📄 Report")
        st.markdown(report)

        st.divider()
        st.subheader("🔗 Sources")
        for i, s in enumerate(sources, 1):
            st.markdown(f'<div class="source-item">{i}. <a href="{s["url"]}" target="_blank">{s["title"]}</a></div>', unsafe_allow_html=True)

        st.divider()
        st.download_button(
            label="⬇️ Download report as .md",
            data=report,
            file_name=f"report_{active_topic[:30].replace(' ', '_')}.md",
            mime="text/markdown"
        )