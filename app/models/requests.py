from pydantic import BaseModel, Field
from typing import Optional

class ComplianceQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language compliance question")
    code_snippet: Optional[str] = Field(
        None, description="Code or requirement text to validate"
    )
    standard: str = Field("MISRA C:2023", description="Technical standard to query against")
    thread_id: Optional[str] = Field(
        None, description="Optional thread ID to continue an existing conversation; a new UUID is generated if omitted"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "Does this function violate any MISRA C:2023 rules?",
                "code_snippet": "def calculate_altitude(pressure: float) -> float:\n    return 44330 * (1 - (pressure / 1013.25) ** 0.1903)",
                "standard": "MISRA C:2023",
            }
        }
    }

class IngestRuleRequest(BaseModel):
    rule_id: str
    standard: str
    section: str
    dal_level: str = Field(..., pattern="^[A-E]$")
    title: str
    full_text: str
    keywords: list[str] = []