import os
import json
import re
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from supabase import create_client

# Load API keys
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Research Agent",
    page_icon="🔍",
    layout="wide"
)

# ─────────────────────────────────────────────
# Dark / Light mode
# ─────────────────────────────────────────────
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

dark = st.session_state.dark_mode

if dark:
    bg = "#0f1117"
    card_bg = "#1e2130"
    border = "#2e3250"
    text = "#ffffff"
    subtext = "#a0aec0"
    input_bg = "#1e2130"
    sidebar_bg = "#13151f"
else:
    bg = "#ffffff"
    card_bg = "#f7f8fa"
    border = "#e2e8f0"
    text = "#1a202c"
    subtext = "#718096"
    input_bg = "#f7f8fa"
    sidebar_bg = "#f0f2f6"

st.markdown(f"""
<style>
    .stApp {{ background-color: {bg}; color: {text}; }}
    h1, h2, h3 {{ color: {text} !important; }}
    p, li, span {{ color: {text}; }}
    [data-testid="metric-container"] {{
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 12px;
        padding: 1rem;
    }}
    .stButton > button {{
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }}
    .stButton > button:hover {{
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        border: none !important;
        color: white !important;
        padding: 0.6rem 2rem !important;
        font-size: 1rem !important;
    }}
    .stTextInput > div > div > input {{
        background: {input_bg} !important;
        border: 1px solid {border} !important;
        border-radius: 10px !important;
        color: {text} !important;
        font-size: 1rem !important;
        padding: 0.75rem 1rem !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {sidebar_bg} !important;
        border-right: 1px solid {border} !important;
    }}
    hr {{ border-color: {border} !important; }}
    div[data-testid="column"] .stButton > button {{
        background: transparent !important;
        border: 1px solid {border} !important;
        color: {text} !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        border-radius: 20px !important;
        padding: 0.4rem 0.8rem !important;
    }}
    div[data-testid="column"] .stButton > button:hover {{
        border-color: #6366f1 !important;
        color: #6366f1 !important;
        background: transparent !important;
    }}
    .source-item {{
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }}
    .source-item a {{ color: #6366f1; }}
    .status-badge {{
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }}
    .badge-green {{
        background: #0d3320;
        color: #3ecf8e;
        border: 1px solid #1a6640;
    }}
    .search-item {{
        font-family: monospace;
        font-size: 0.85rem;
        color: #6366f1;
        padding: 0.3rem 0;
    }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Supabase history helpers
# ─────────────────────────────────────────────
def load_history():
    try:
        res = supabase.table("Reports").select("*").order("id", desc=True).limit(20).execute()
        return res.data or []
    except:
        return []

def save_to_history(topic, report, sources):
    try:
        supabase.table("Reports").insert({
            "topic": topic,
            "report": report,
            "sources": json.dumps(sources),
            "date": datetime.now().strftime("%B %d, %Y — %H:%M")
        }).execute()
    except Exception as e:
        st.warning(f"Could not save to history: {e}")

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
            snippet = r['content'][:300]
            output += f"[{i}] {r['title']}\nURL: {r['url']}\n{snippet}\n\n"
        return output
    except Exception as e:
        return f"Search failed: {str(e)}"

# ─────────────────────────────────────────────
# Get search queries
# ─────────────────────────────────────────────
def get_search_queries(topic):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": "You are a research planner. Given a topic, return exactly 5 search queries as a JSON array of strings. Return ONLY the JSON array, nothing else."
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
# Write report
# ─────────────────────────────────────────────
def write_report(topic, search_results):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2048,
        messages=[
            {
                "role": "system",
                "content": "You are an expert research writer. Write a comprehensive, well-structured report in markdown with clear sections, headers, key findings, analysis, and a conclusion."
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
    mode_label = "☀️ Light mode" if dark else "🌙 Dark mode"
    if st.button(mode_label, use_container_width=True):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

    st.divider()
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
                    item["sources"] = json.loads(item["sources"]) if isinstance(item["sources"], str) else item["sources"]
                    st.session_state.loaded_report = item

# ─────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────
st.markdown("# 🔍 Research Agent")
st.caption("Powered by Groq + Tavily — free, fast, and private")
st.divider()

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