import os
from dotenv import load_dotenv

# Load environment variables before importing app modules
# This ensures your GEMINI_API_KEY is available to config.py
load_dotenv()

from app.graph.nodes.orchestrator import orchestrate
from app.models.state import ComplianceState

def run_tests():
    print("--- Testing Orchestrator Node (MISRA-C) ---\n")

    # Test Case 1: Search Intent
    state_search: ComplianceState = {
        "query": "Find the MISRA-C rule that talks about using goto statements.",
        "code_snippet": "",
        "standard": "MISRA-C"
    }
    
    # Test Case 2: Validate Intent
    state_validate: ComplianceState = {
        "query": "Check if this code violates any rules.",
        "code_snippet": "void my_func() { int *ptr = NULL; *ptr = 10; }",
        "standard": "MISRA-C"
    }

    # Test Case 3: Explain Intent
    state_explain: ComplianceState = {
        "query": "Why is dynamic memory allocation like malloc() forbidden in MISRA-C?",
        "code_snippet": "",
        "standard": "MISRA-C"
    }

    test_cases = [
        ("Search Test", state_search),
        ("Validate Test", state_validate),
        ("Explain Test", state_explain)
    ]

    for name, state in test_cases:
        print(f"Running {name}...")
        print(f"Query: {state['query']}")
        try:
            # Call the node function directly
            result = orchestrate(state)
            print(f"Result Intent: {result['intent']}")
            print(f"Reasoning:   {result['orchestrator_reasoning']}")
        except Exception as e:
            print(f"Error: {e}")
        print("-" * 40)

if __name__ == "__main__":
    run_tests()