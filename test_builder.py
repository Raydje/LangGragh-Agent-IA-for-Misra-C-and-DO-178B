import asyncio
from dotenv import load_dotenv
from app.graph.builder import build_graph

# Load API keys (Gemini, Pinecone, MongoDB, etc.)
load_dotenv()

async def run_end_to_end_test():
    print("🚀 Compiling the LangGraph workflow...")
    app = build_graph()

    # We will simulate a user asking to validate a piece of code
    # that intentionally violates MISRA-C Rule 15.6 (missing braces)
    initial_state = {
        "query": "Check if this C code complies with MISRA-C.",
        "code_snippet": """
int calculate(int x) {
    if (x > 0)
        return x * 2;
    return 0;
}
        """,
        "standard": "MISRA-C",
        "iteration_count": 0,
        "max_iterations": 3,  # Maximum times the critique loop can run
        "critique_history": [],
    }

    print("\n" + "="*50)
    print("🏃 RUNNING THE GRAPH (Streaming Node-by-Node)...")
    print("="*50)

    # .astream() lets us watch the graph execute step-by-step asynchronously
    try:
        async for output in app.astream(initial_state):
            # output is a dict where the key is the node name, and value is the state update
            for node_name, state_update in output.items():
                print(f"\n✅ Finished Node: [ {node_name.upper()} ]")

                # Print interesting bits depending on which node just ran
                if node_name == "orchestrator":
                    print(f"   -> Detected Intent: {state_update.get('intent')}")

                elif node_name == "rag":
                    rules = state_update.get('retrieved_rules', [])
                    print(f"   -> Retrieved {len(rules)} rules from DB.")

                elif node_name == "validation":
                    print(f"   -> Compliant? {state_update.get('is_compliant')}")
                    print(f"   -> Iteration Count: {state_update.get('iteration_count')}")

                elif node_name == "critique":
                    print(f"   -> Approved by Reviewer? {state_update.get('critique_approved')}")
                    if not state_update.get('critique_approved'):
                        print(f"   -> Critique Feedback: {state_update.get('critique_feedback')}")

                elif node_name == "assemble":
                    print("\n" + "="*50)
                    print("🎯 FINAL ASSEMBLED RESPONSE:")
                    print("="*50)
                    print(state_update.get('final_response'))

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")

if __name__ == "__main__":
    asyncio.run(run_end_to_end_test())