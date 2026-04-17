import requests
import streamlit as st

# Configuration
BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="MISRA C AI Validator",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="expanded",
)

# Custom CSS for a modern look
st.markdown(
    """
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .status-card {
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border: 1px solid #343a40;
        background-color: #212529;
        color: #f8f9fa;
    }
    .status-card code {
        background-color: #343a40;
        color: #ff79c6;
        padding: 0.2rem 0.4rem;
        border-radius: 4px;
    }
    .compliant, .non-compliant {
        border-left: 8px solid #495057;
    }
    .stTextArea textarea {
        font-family: 'Source Code Pro', monospace;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
with st.sidebar:
    st.title("🛡️ MISRA AI Validator")
    st.markdown("---")

    if st.session_state["token"] is None:
        st.subheader("🔒 Authentication")
        auth_mode = st.radio("Mode", ["Login", "Register"], label_visibility="collapsed")

        email = st.text_input("Email", placeholder="email@example.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")

        admin_token = None
        if auth_mode == "Register":
            admin_token = st.text_input(
                "Admin Token (optional)", type="password", placeholder="Leave blank for standard user"
            )

        if st.button(auth_mode, use_container_width=True, type="primary"):
            if auth_mode == "Register":
                payload = {"email": email, "password": password}
                if admin_token:
                    payload["admin_registration_token"] = admin_token
                res = requests.post(f"{BASE_URL}/auth/register", json=payload)
                if res.status_code == 201:
                    st.success("Registered! Please login.")
                else:
                    st.error("Registration failed.")

            elif auth_mode == "Login":
                res = requests.post(f"{BASE_URL}/auth/token", data={"username": email, "password": password})
                if res.status_code == 200:
                    st.session_state["token"] = res.json().get("access_token")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
    else:
        st.success("✅ Authenticated Session")

        try:
            health_res = requests.get(f"{BASE_URL}/health", timeout=2)
            if health_res.status_code == 200 and health_res.json().get("status") == "healthy":
                st.caption("🟢 Backend: Online")
            else:
                st.caption("🟡 Backend: Degraded")
        except Exception:
            st.caption("🔴 Backend: Offline")

        if st.button("Logout", use_container_width=True):
            st.session_state["token"] = None
            st.rerun()

        st.markdown("---")
        menu = st.radio(
            "Navigation",
            ["Code Validator", "Session History", "My Usage", "Time-Travel Replay", "Admin: Seed & Ingest"],
        )

# --- MAIN CONTENT ---

if st.session_state["token"] is None:
    st.info("👋 Welcome! Please login or register from the sidebar to start analyzing code.")
    st.stop()

if menu == "Code Validator":
    st.title("👨‍💻 Analyze C/C++ Code")
    st.markdown("Provide your code snippet and a custom query for the multi-agent analysis.")

    # Main Input Area
    with st.container():
        col_q, col_std, col_s = st.columns([3, 1, 1])
        with col_q:
            query = st.text_input(
                "Compliance Query",
                value="Analyze this code for MISRA compliance.",
                help="Specify what you want the agents to focus on (e.g., 'Is this memory compliant?', 'Check for Rule 12.1')",
            )
        with col_std:
            standard = st.selectbox(
                "Standard",
                options=["MISRA C:2023", "MISRA C++:2023"],
                help="Select the compliance standard to validate against.",
            )
        with col_s:
            use_thread = st.toggle("Continue Session", value=False, help="Resume from the last known state (Thread ID)")

        code_snippet = st.text_area("C/C++ Source Code", height=300, placeholder="// Paste your code here...")

        if st.button("🚀 Run Multi-Agent Analysis", type="primary", use_container_width=True):
            if not code_snippet:
                st.warning("Please provide a code snippet to analyze.")
            else:
                with st.spinner("Agents are critiquing your code..."):
                    payload = {"query": query, "code_snippet": code_snippet, "standard": standard}
                    if use_thread and st.session_state["thread_id"]:
                        payload["thread_id"] = st.session_state["thread_id"]

                    try:
                        res = requests.post(f"{BASE_URL}/query", json=payload, headers=get_headers())
                        if res.status_code == 200:
                            data = res.json()
                            st.session_state["thread_id"] = data.get("thread_id")

                            st.divider()

                            # Modern Status Display
                            is_compliant = data.get("is_compliant")
                            status_class = "compliant" if is_compliant else "non-compliant"
                            status_icon = "✅" if is_compliant else "❌"
                            status_text = "Compliant" if is_compliant else "Non-Compliant"

                            st.markdown(
                                f"""
                                <div class="status-card {status_class}">
                                    <h3 style='margin:0;'>{status_icon} Result: {status_text}</h3>
                                    <small>Thread ID: <code>{data.get("thread_id")}</code></small>
                                </div>
                            """,
                                unsafe_allow_html=True,
                            )

                            res_col1, res_col2 = st.columns(2)
                            with res_col1:
                                st.subheader("🧠 Agent Explanation")
                                explanation = data.get("final_response") or data.get("remediation_explanation")
                                if explanation:
                                    st.info(explanation)
                                else:
                                    st.write("No explanation provided.")

                            with res_col2:
                                if data.get("fixed_code_snippet"):
                                    st.subheader("🛠️ Suggested Remediation")
                                    st.code(data.get("fixed_code_snippet"), language="c")
                                else:
                                    st.subheader("🛠️ Remediation")
                                    st.success("No code changes suggested.")

                            # Token usage & cost
                            usage = data.get("total_tokens_usage") or {}
                            st.divider()
                            st.subheader("📊 Token Usage & Cost")
                            u_col1, u_col2, u_col3, u_col4 = st.columns(4)
                            u_col1.metric("Prompt Tokens", usage.get("prompt_tokens", "—"))
                            u_col2.metric("Completion Tokens", usage.get("completion_tokens", "—"))
                            u_col3.metric("Total Tokens", usage.get("total_tokens", "—"))
                            u_col4.metric(
                                "Estimated Cost",
                                f"${usage.get('estimated_cost', 0):.6f}"
                                if usage.get("estimated_cost") is not None
                                else "—",
                            )
                        else:
                            st.error(f"Analysis failed ({res.status_code}): {res.text}")
                    except Exception as e:
                        st.error(f"Connection Error: {str(e)}")

elif menu == "Session History":
    st.title("📜 Session History")
    active_id = st.session_state["thread_id"]
    default_id = active_id or ""
    thread_input = st.text_input("Thread ID", value=default_id, placeholder="Enter a thread ID to query")
    if active_id and active_id == thread_input:
        st.caption("Using active session thread.")

    if st.button("Fetch History", type="primary"):
        if not thread_input:
            st.warning("Please enter a Thread ID.")
        else:
            res = requests.get(f"{BASE_URL}/history/{thread_input}", headers=get_headers())
            if res.status_code == 200:
                st.json(res.json())
            else:
                st.error(f"Failed to fetch history ({res.status_code}).")

elif menu == "My Usage":
    st.title("📈 My Usage")
    st.markdown("View your cumulative token consumption and cost across all queries.")

    if st.button("Fetch My Usage", type="primary"):
        res = requests.get(f"{BASE_URL}/usage", headers=get_headers())
        if res.status_code == 200:
            udata = res.json()
            u_col1, u_col2, u_col3 = st.columns(3)
            u_col1.metric("Total Requests", udata.get("total_requests", "—"))
            u_col2.metric("Total Cost", f"${udata.get('total_cost', 0):.6f}")
            u_col3.metric("User", udata.get("email") or udata.get("user_id", "—"))

            logs = udata.get("recent_logs", [])
            if logs:
                st.divider()
                st.subheader("Recent Activity")
                for entry in logs:
                    with st.expander(
                        f"{entry.get('timestamp', '')} — {entry.get('endpoint', '')} ({entry.get('status_code', '')})",
                        expanded=False,
                    ):
                        l_col1, l_col2, l_col3, l_col4 = st.columns(4)
                        l_col1.metric("Prompt Tokens", entry.get("prompt_tokens", "—"))
                        l_col2.metric("Completion Tokens", entry.get("completion_tokens", "—"))
                        l_col3.metric("Total Tokens", entry.get("total_tokens", "—"))
                        l_col4.metric("Cost", f"${entry.get('estimated_cost', 0):.6f}")
                        if entry.get("thread_id"):
                            st.caption(f"Thread: `{entry['thread_id']}`")
        else:
            st.error(f"Failed to fetch usage ({res.status_code}): {res.text}")

elif menu == "Time-Travel Replay":
    st.title("⏪ Time Travel Debugging")
    st.markdown("Fork the execution from a specific state checkpoint.")

    t_col1, t_col2 = st.columns(2)
    with t_col1:
        thread_to_replay = st.text_input("Thread ID", value=st.session_state["thread_id"] or "")
    with t_col2:
        checkpoint_id = st.text_input("Checkpoint ID")

    if st.button("Replay State", type="primary", use_container_width=True):
        if thread_to_replay and checkpoint_id:
            with st.spinner("Replaying graph..."):
                res = requests.post(f"{BASE_URL}/replay/{thread_to_replay}/{checkpoint_id}", headers=get_headers())
                if res.status_code == 200:
                    st.write(res.json())
                else:
                    st.error(f"Replay failed: {res.text}")
        else:
            st.error("Please provide both Thread ID and Checkpoint ID.")

elif menu == "Admin: Seed & Ingest":
    st.title("⚙️ Vector DB Administration")
    st.markdown("Manage the rules database and RAG pipeline.")

    if st.button("Seed Rules Database", type="secondary", use_container_width=True):
        with st.spinner("Generating embeddings..."):
            res = requests.post(f"{BASE_URL}/seed", headers=get_headers())
            if res.status_code == 200:
                st.success("Database successfully seeded!")
            else:
                st.error(f"Seeding failed: {res.text}")
