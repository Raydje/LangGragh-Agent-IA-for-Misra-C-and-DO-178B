"""
Seed data ingestion script.
Run with: python -m app.data.ingest
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

from pymongo import ReplaceOne

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.embedding_service import EmbeddingService
from app.services.mongodb_service import MongoDBService
from app.services.pinecone_service import PineconeService
from app.services.service_container import create_service_container
from app.utils import logger


def parse_misra_file(filepath: str) -> list[dict]:
    """
    Parses the MISRA C:2023 text file and extracts structured metadata.
    """
    rules = []

    # Resolve the path relative to this script
    # app/data/ingest.py -> project root is 3 levels up
    base_dir = Path(__file__).resolve().parent.parent.parent
    file_path = base_dir / filepath

    logger.info("📂 Attempting to read file", file_path=file_path)

    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error("Error: Could not find file", file_path=file_path)
        return []

    current_rule: dict[str, Any] | None = None

    # Regex to match lines like: "Rule 1.1    Required", "Dir 4.1\tRequired", or "Rule 22.15\tMandatory"
    header_pattern = re.compile(r"^(Rule|Dir)\s+(\d+)\.(\d+)\s+(.+)$")

    for line in lines:
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        header_match = header_pattern.match(line)

        if header_match:
            # If we were already building a rule, save it before starting a new one
            if current_rule and current_rule.get("full_text"):
                rules.append(current_rule)

            # Extract metadata using regex groups
            rule_type = header_match.group(1).upper()  # "RULE" or "DIR"
            section = int(header_match.group(2))
            rule_number = int(header_match.group(3))
            category = header_match.group(4).strip()

            # Initialize the new rule object
            current_rule = {
                "scope": "MISRA C:2023",
                "rule_type": rule_type,
                "section": section,
                "rule_number": rule_number,
                "category": category,
                "full_text": "",
            }
        elif current_rule:
            # If it's not a header, it must be the rule text.
            # Append it to the current rule's full_text.
            if current_rule["full_text"]:  # multiple lines of text for a single rule
                current_rule["full_text"] += " " + line
            else:
                current_rule["full_text"] = line

    # Don't forget to add the very last rule in the file!
    if current_rule and current_rule.get("full_text"):
        rules.append(current_rule)

    return rules


# MISRA C++:2023 parser — handles both Format A (Rule-X.Y.Z) and Format B (Rule X.Y.Z    Category)
_CPP_FORMAT_A_HEADER = re.compile(r"^(Rule|Dir)-(\d+)\.(\d+)\.(\d+)\s*(.*)")
_CPP_FORMAT_B_HEADER = re.compile(r"^(Rule|Dir)\s+(\d+)\.(\d+)\.(\d+)\s+(Required|Advisory|Mandatory|Assisted)\b")
# Matches a category keyword (optionally preceded by description text) followed by
# "Decidable|Undecidable Yes|No" — used to extract category from Format A continuation lines.
_CPP_CATEGORY_SUFFIX = re.compile(
    r"^(.*?)\s*(Required|Advisory|Mandatory|Assisted)\s+(?:Decidable|Undecidable)\s+(?:Yes|No)\s*$"
)


def parse_misra_cpp_file(filepath: str) -> list[dict]:
    """
    Parses the MISRA C++:2023 text file and extracts structured metadata.

    The file contains two line formats:
    - Format A: ``Rule-X.Y.Z optional_inline_text`` with category on a
      later continuation line (e.g. ``Advisory Decidable Yes``).
    - Format B: ``Rule X.Y.Z    Category`` with the description on the
      next line.

    All C++ rule numbers have three parts (section.group.rule_number),
    stored as separate ``section``, ``group``, and ``rule_number`` int fields.
    """
    rules: list[dict] = []

    base_dir = Path(__file__).resolve().parent.parent.parent
    file_path = base_dir / filepath

    logger.info("📂 Attempting to read file", file_path=file_path)

    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error("Error: Could not find file", file_path=file_path)
        return []

    current_rule: dict[str, Any] | None = None

    for line in lines:
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        # --- Format B header: "Rule X.Y.Z    Required" ---
        m_b = _CPP_FORMAT_B_HEADER.match(line)
        if m_b:
            if current_rule and current_rule.get("full_text") and current_rule.get("category"):
                rules.append(current_rule)
            current_rule = {
                "scope": "MISRA C++:2023",
                "rule_type": "RULE" if m_b.group(1) == "Rule" else "DIR",
                "section": int(m_b.group(2)),
                "group": int(m_b.group(3)),
                "rule_number": int(m_b.group(4)),
                "category": m_b.group(5),
                "full_text": "",
            }
            continue

        # --- Format A header: "Rule-X.Y.Z optional_inline_text" ---
        m_a = _CPP_FORMAT_A_HEADER.match(line)
        if m_a:
            if current_rule and current_rule.get("full_text") and current_rule.get("category"):
                rules.append(current_rule)
            inline = m_a.group(5).strip()
            category = None
            full_text = ""

            # Check if the inline text already contains the category suffix
            m_cat = _CPP_CATEGORY_SUFFIX.match(inline)
            if m_cat:
                full_text = m_cat.group(1).strip()
                category = m_cat.group(2)
            else:
                full_text = inline

            current_rule = {
                "scope": "MISRA C++:2023",
                "rule_type": "RULE" if m_a.group(1) == "Rule" else "DIR",
                "section": int(m_a.group(2)),
                "group": int(m_a.group(3)),
                "rule_number": int(m_a.group(4)),
                "category": category,
                "full_text": full_text,
            }
            continue

        # --- Continuation line ---
        if current_rule is None:
            continue

        if current_rule["category"] is None:
            # Format A rule — still looking for the category marker
            m_cat = _CPP_CATEGORY_SUFFIX.match(line)
            if m_cat:
                desc_part = m_cat.group(1).strip()
                current_rule["category"] = m_cat.group(2)
                if desc_part:
                    if current_rule["full_text"]:
                        current_rule["full_text"] += " " + desc_part
                    else:
                        current_rule["full_text"] = desc_part
            else:
                if current_rule["full_text"]:
                    current_rule["full_text"] += " " + line
                else:
                    current_rule["full_text"] = line
        else:
            # Format B rule — append description text
            if current_rule["full_text"]:
                current_rule["full_text"] += " " + line
            else:
                current_rule["full_text"] = line

    # Save the last rule
    if current_rule and current_rule.get("full_text") and current_rule.get("category"):
        rules.append(current_rule)

    return rules


async def upload_to_mongodb(rules: list[dict], svc: MongoDBService):
    """Uploads parsed rules to MongoDB asynchronously."""
    if not rules:
        logger.warning("No rules to upload.")
        return

    logger.info("Connecting to MongoDB Atlas...")
    try:
        await svc.create_indexes()
    except Exception:
        logger.error("Error creating indexes in MongoDB")
        return

    logger.info("Preparing to insert/update rules...", number_of_rules=len(rules))

    operations = []
    for rule in rules:
        query = {
            "scope": rule["scope"],
            "rule_type": rule["rule_type"],
            "section": rule["section"],
            "rule_number": rule["rule_number"],
        }
        if "group" in rule:
            query["group"] = rule["group"]
        operations.append(ReplaceOne(query, rule, upsert=True))

    if operations:
        result = await svc.collection.bulk_write(operations)
        logger.info("✅ Successfully processed rules in MongoDB!", number_of_rules=len(rules))
        logger.info("   - Inserted:", number_inserted=result.upserted_count)
        logger.info("   - Modified:", number_modified=result.modified_count)


async def main(mongodb: MongoDBService, pinecone: PineconeService, embedder: EmbeddingService) -> dict:
    total_rules = 0
    total_vectors = 0

    for parse_fn, filepath in [
        (parse_misra_file, "data/misra_c_2023__headlines_for_cppcheck.txt"),
        (parse_misra_cpp_file, "data/misra_c_plus_plus_2023__headlines_for_cppcheck.txt"),
    ]:
        parsed_rules = parse_fn(filepath)

        if parsed_rules:
            standard = parsed_rules[0].get("scope", "unknown")
            logger.info("✅ Successfully parsed rules!", number_of_rules=len(parsed_rules), standard=standard)
            await upload_to_mongodb(parsed_rules, mongodb)
            vectors_upserted = await embedder.embed_and_store(parsed_rules, pinecone)
            total_rules += len(parsed_rules)
            total_vectors += vectors_upserted

    return {"rules_ingested": total_rules, "vectors_upserted": total_vectors}


async def run_ingest_cli() -> None:
    """CLI entry point — manages service lifecycle via the centralised container."""
    async with create_service_container() as container:
        result = await main(
            mongodb=container.mongodb,
            pinecone=container.pinecone,
            embedder=container.embedding,
        )
        logger.info("Ingestion complete", **result)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_ingest_cli())
