import requests
import streamlit as st

# Configuration
BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(page_title="MISRA C AI Validator", layout="wide", page_icon="🛡️")

# Initialize session state for Authentication
if "token" not in st.session_state:
    st.session_state["token"] = None
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = None


def get_headers():
    if st.session_state["token"]:
        return {"Authorization": f"Bearer {st.session_state['token']}"}
    return {}


# --- SIDEBAR NAVIGATION ---
st.sidebar.title("🛡️ MISRA AI Validator")

# Authentication UI
if st.session_state["token"] is None:
    st.sidebar.subheader("🔒 Authentication")
    auth_mode = st.sidebar.radio("Mode", ["Login", "Register"])

    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button(auth_mode):
        if auth_mode == "Register":
            res = requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password})
            if res.status_code == 201:
                st.sidebar.success("Registered! Please login.")
            else:
                st.sidebar.error("Registration failed.")

        elif auth_mode == "Login":
            # Assuming standard OAuth2 password bearer form format for FastAPI
            res = requests.post(f"{BASE_URL}/auth/token", data={"username": email, "password": password})
            if res.status_code == 200:
                st.session_state["token"] = res.json().get("access_token")
                st.sidebar.success("Logged in!")
                st.rerun()
            else:
                st.sidebar.error("Invalid credentials.")
else:
    st.sidebar.success("✅ Logged In")

    # Optional Health Check Indicator
    try:
        health_res = requests.get(f"{BASE_URL}/health")
        if health_res.status_code == 200 and health_res.json().get("status") == "healthy":
            st.sidebar.success("🟢 Systems Healthy")
        else:
            st.sidebar.warning("🟡 Systems Degraded")
    except requests.exceptions.ConnectionError:
        st.sidebar.error("🔴 Backend Offline")

    if st.sidebar.button("Logout"):
        st.session_state["token"] = None
        st.rerun()

    # App Navigation Menu
    menu = st.sidebar.radio("Menu", ["Code Validator", "Session History", "Time-Travel Replay", "Admin: Seed & Ingest"])

    # --- 1. CODE VALIDATOR ---
    if menu == "Code Validator":
        st.title("👨‍💻 Analyze C/C++ Code")
        code_snippet = st.text_area("Paste C/C++ Code here", height=250)

        # Optional: resume a thread
        use_thread = st.checkbox("Continue previous session (use stored thread_id)?", value=False)

        if st.button("Run Multi-Agent Analysis", type="primary"):
            if code_snippet:
                with st.spinner("LangGraph Agents are critiquing your code..."):
                    payload = {"query": "Analyze this code for MISRA compliance.", "code_snippet": code_snippet}
                    if use_thread and st.session_state["thread_id"]:
                        payload["thread_id"] = st.session_state["thread_id"]

                    res = requests.post(f"{BASE_URL}/query", json=payload, headers=get_headers())

                    if res.status_code == 200:
                        data = res.json()
                        st.session_state["thread_id"] = data.get("thread_id")  # Save for history/replay

                        st.success(f"Analysis Complete! (Thread: {data.get('thread_id')})")

                        col1, col2 = st.columns(2)
                        with col1:
                            if data.get("is_compliant"):
                                st.success("✅ Code is MISRA compliant!")
                            else:
                                st.error("❌ Non-compliance detected.")

                            st.markdown("### Agent Explanation")
                            st.write(data.get("final_response") or data.get("remediation_explanation"))

                        with col2:
                            if data.get("fixed_code_snippet"):
                                st.markdown("### 🛠️ Suggested Remediation")
                                st.code(data.get("fixed_code_snippet"), language="c")
                    else:
                        st.error(f"Error: {res.text}")

    # --- 2. SESSION HISTORY ---
    elif menu == "Session History":
        st.title("📜 Session History")
        st.info(f"Current Active Thread ID: {st.session_state['thread_id']}")
        if st.button("Fetch History"):
            if st.session_state["thread_id"]:
                res = requests.get(f"{BASE_URL}/history/{st.session_state['thread_id']}", headers=get_headers())
                if res.status_code == 200:
                    st.json(res.json())
                else:
                    st.error("Failed to fetch history.")
            else:
                st.warning("No active thread ID. Please run a validation first.")

    # --- 3. TIME TRAVEL REPLAY ---
    elif menu == "Time-Travel Replay":
        st.title("⏪ Time Travel Debugging")
        st.markdown("Fork and re-execute the LangGraph from a specific state checkpoint.")
        thread_to_replay = st.text_input("Thread ID", value=st.session_state["thread_id"] or "")
        checkpoint_id = st.text_input("Checkpoint ID (from history)")

        if st.button("Replay State"):
            if not thread_to_replay or not checkpoint_id:
                st.error("Please provide both Thread ID and Checkpoint ID.")
            else:
                with st.spinner("Replaying graph..."):
                    res = requests.post(f"{BASE_URL}/replay/{thread_to_replay}/{checkpoint_id}", headers=get_headers())
                    if res.status_code == 200:
                        st.write(res.json())
                    else:
                        st.error(f"Replay failed: {res.text}")

    # --- 4. ADMIN: SEED & INGEST ---
    elif menu == "Admin: Seed & Ingest":
        st.title("⚙️ Vector DB Administration")
        st.markdown("Manage the RAG pipelines (Pinecone & MongoDB).")

        if st.button("Seed Rules Database", type="secondary"):
            with st.spinner("Parsing MISRA rules and generating embeddings..."):
                res = requests.post(f"{BASE_URL}/seed", headers=get_headers())
                if res.status_code == 200:
                    st.success("Database successfully seeded with MISRA rules!")
                else:
                    st.error(f"Seeding failed: {res.text}")
