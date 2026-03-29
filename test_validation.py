import os
from dotenv import load_dotenv
from app.graph.nodes.validation import validation_node

# 1. Load environment variables (Make sure GEMINI_API_KEY is in your .env)
load_dotenv()

def run_test():
    print("Setting up mock state...")
    
    # 2. Mock a ComplianceState dictionary
    # We'll use a classic MISRA violation: missing braces around an if-statement body (Rule 15.6)
    mock_state = {
        "query": "Check this code for MISRA C:2023 compliance.",
        "code_snippet": """
int calculate(int x) {
    if (x > 0) 
        return x * 2; /* MISRA Violation: Needs braces */
    return 0;
}
        """,
        "retrieved_rules": [
            {
                "rule_id": "Rule 15.6",
                "dal_level": "Required",  # Re-using dal_level for Category as per your prompt
                "title": "The body of an iteration-statement or a selection-statement shall be a compound-statement",
                "full_text": "The body of an if, else, while, do ... while or for statement shall always be enclosed in braces."
            }
        ],
        "critique_feedback": "",
        "iteration_count": 0
    }

    print("Invoking validation_node...")
    # 3. Call the node directly
    result = validation_node(mock_state)
    
    print("\n--- VALIDATION RESULT ---")
    import pprint
    pprint.pprint(result)

if __name__ == "__main__":
    run_test()