from typing import Any

import structlog

from app.config import get_settings


def calculate_gemini_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Calculates the estimated cost for model usage."""
    settings = get_settings()
    input_cost = (prompt_tokens / 1_000_000) * settings.llm_input_cost_per_1m
    output_cost = (completion_tokens / 1_000_000) * settings.llm_output_cost_per_1m
    return input_cost + output_cost


def extracting_tokens_metadata(raw_result: dict[str, Any]) -> dict:
    usage = getattr(raw_result.get("raw"), "usage_metadata", None) or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    estimated_cost = calculate_gemini_cost(input_tokens, output_tokens)
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": estimated_cost,
    }


logger = structlog.get_logger()

rule_naming_mapping_critique = {
    "MISRA C:2023": '"MISRA_DIR_4.7" or "MISRA_RULE_17.4"',
    "MISRA C++:2023": '"MISRA_DIR_4.5.7" or "MISRA_RULE_2.17.4"',
}
rule_naming_mapping_validation = {
    "MISRA C:2023": [
        '"MISRA_DIR_X.Y" (e.g., "MISRA_DIR_4.7 (Mandatory)")',
        '"MISRA_RULE_X.Y" (e.g., "MISRA_RULE_17.4 (Required)", "MISRA_RULE_1.2 (Advisory)")',
        '"MISRA_RULE_17.4 (Required): ..." or "MISRA_DIR_4.7 (Mandatory): ..."',
        '["MISRA_RULE_17.4", "MISRA_DIR_4.7"]',
    ],
    "MISRA C++:2023": [
        '"MISRA_DIR_X.Y.Z" (e.g., "MISRA_DIR_4.5.7 (Mandatory)")',
        '"MISRA_RULE_X.Y.Z" (e.g., "MISRA_RULE_2.17.4 (Required)", "MISRA_RULE_1.2.4 (Advisory)")',
        '"MISRA_RULE_17.4.1 (Required): ..." or "MISRA_DIR_4.7.2 (Mandatory): ..."',
        '["MISRA_RULE_2.17.4", "MISRA_DIR_4.5.7"]',
    ],
}
