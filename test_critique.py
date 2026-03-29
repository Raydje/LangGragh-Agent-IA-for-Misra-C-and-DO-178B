from dotenv import load_dotenv
import pprint

load_dotenv()

from app.graph.nodes.critique import critique_node


def run(label, expected_approved, state):
    print(f"\n{'='*55}")
    print(f"SCENARIO: {label}")
    print(f"Expected: approved={expected_approved}")
    print('='*55)
    result = critique_node(state)
    pprint.pprint(result)
    actual = result.get("critique_approved")
    status = "OK" if actual == expected_approved else "FAIL"
    print(f">> {status} (got approved={actual})")


# --- SCENARIO 1: Should APPROVE ---
# Correct validation: Rule 15.6 cited, is_compliant matches, code referenced.
run(
    label="APPROVE — correct violation report",
    expected_approved=True,
    state={
        "code_snippet": (
            "int calculate(int x) {\n"
            "    if (x > 0)\n"
            "        return x * 2;\n"  # missing braces
            "    return 0;\n"
            "}"
        ),
        "retrieved_rules": [
            {
                "rule_id": "Rule 15.6",
                "dal_level": "Required",
                "title": "The body of an iteration-statement or a selection-statement shall be a compound-statement",
                "full_text": "The body of an if, else, while, do...while or for statement shall always be enclosed in braces.",
            }
        ],
        "cited_rules": ["Rule 15.6"],
        "is_compliant": False,
        "validation_result": (
            "The code violates Rule 15.6. On line 3, the body of the 'if (x > 0)' "
            "statement is not enclosed in braces. A compound-statement (braces) is "
            "required for all selection-statement bodies under MISRA C:2023."
        ),
    },
)

# --- SCENARIO 2: Should REJECT — Rule Hallucination (Criterion 1) ---
# Agent cites Rule 99.9 which was never retrieved.
run(
    label="REJECT — hallucinated rule ID (Rule 99.9 not retrieved)",
    expected_approved=False,
    state={
        "code_snippet": "int main() { return 0; }",
        "retrieved_rules": [
            {
                "rule_id": "Rule 1.1",
                "dal_level": "Required",
                "title": "The program shall contain no violations of the standard C syntax.",
                "full_text": "All code shall conform to ISO 9899:2011 (C11).",
            }
        ],
        "cited_rules": ["Rule 99.9"],
        "is_compliant": False,
        "validation_result": (
            "The code violates Rule 99.9 which forbids returning 0 from main."
        ),
    },
)

# --- SCENARIO 3: Should REJECT — Logical Inconsistency (Criterion 2) ---
# validation_result says "fully compliant" but is_compliant=False.
run(
    label="REJECT — logical contradiction (text says compliant, bool says False)",
    expected_approved=False,
    state={
        "code_snippet": (
            "int flag = 2;\n"
            "if (flag) { do_something(); }"  # non-boolean in condition
        ),
        "retrieved_rules": [
            {
                "rule_id": "Rule 14.4",
                "dal_level": "Required",
                "title": "The controlling expression of an if-statement shall be essentially Boolean.",
                "full_text": "The controlling expression of an if or iteration-statement shall have essentially Boolean type.",
            }
        ],
        "cited_rules": ["Rule 14.4"],
        "is_compliant": False,
        "validation_result": (
            "The code is fully compliant with all retrieved MISRA C:2023 rules."
        ),
    },
)

# --- SCENARIO 4: Should REJECT — Not grounded in code (Criterion 3) ---
# Explanation is too generic, does not reference the actual code at all.
run(
    label="REJECT — generic explanation, not grounded in the code",
    expected_approved=False,
    state={
        "code_snippet": (
            "char buf[10];\n"
            "strcpy(buf, input);"
        ),
        "retrieved_rules": [
            {
                "rule_id": "Rule 21.14",
                "dal_level": "Required",
                "title": "The Standard Library function memcmp shall not be used to compare null-terminated strings.",
                "full_text": "The behaviour of memcmp is undefined if the objects pointed to are not of the sizes specified.",
            }
        ],
        "cited_rules": ["Rule 21.14"],
        "is_compliant": False,
        "validation_result": (
            "There may be some potential issues with standard library usage in C programs "
            "that developers should be mindful of when writing embedded software."
        ),
    },
)
