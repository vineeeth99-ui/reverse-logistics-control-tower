
"""Grounded RAG assistant for the Reverse Logistics Control Tower."""

import json
import logging
import time

from src.services.llm_service import generate_response
from src.services.rag_service import search_documents

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the Reverse Logistics Control Tower assistant.

Rules:
1. Use operational context for current operational facts.
2. Use retrieved documents only for documented business rules.
3. Never invent IDs, statuses, dates, or counts.
4. Clearly identify missing information.
5. Separate verified facts from recommendations.
6. Never claim to have changed database records.
7. Potential delay is not proof of a missed delivery commitment.
8. Keep answers concise, usually under 150 words.
9. Complete every sentence and bullet point.
10. Never merge separate numbers or labels.
11. Do not calculate totals when the supplied context already gives them.
12. End with a complete sentence.
"""


def _format_number(value):
    """Format a numeric value consistently."""
    return "{:,.2f}".format(float(value or 0))


def _is_workload_question(question):
    """Recognize requests for a combined return/repair summary."""
    text = question.lower()

    return (
        any(word in text for word in ("return", "returns", "rma"))
        and any(word in text for word in ("repair", "repairs"))
        and any(
            word in text
            for word in ("summar", "workload", "overview", "status")
        )
    )


def _format_workload_summary(context):
    """Create a factual workload summary without LLM arithmetic."""

    return_rows = context.get("return_status_counts", [])
    repair_rows = context.get("repair_summary", [])

    if not return_rows and not repair_rows:
        return (
            "Return and repair workload data is not available in the "
            "operational context. Check the selected database and "
            "the context queries."
        )

    return_total = sum(
        int(row.get("total", 0) or 0)
        for row in return_rows
    )

    repair_total = sum(
        int(row.get("total", 0) or 0)
        for row in repair_rows
    )

    completed_total = sum(
        int(row.get("total", 0) or 0)
        for row in repair_rows
        if str(row.get("repair_status", "")).strip().lower()
        in ("completed", "complete", "closed")
    )

    open_total = repair_total - completed_total

    total_repair_cost = sum(
        float(row.get("repair_cost", 0) or 0)
        for row in repair_rows
    )

    open_repair_cost = sum(
        float(row.get("repair_cost", 0) or 0)
        for row in repair_rows
        if str(row.get("repair_status", "")).strip().lower()
        not in ("completed", "complete", "closed")
    )

    lines = [
        "Current return and repair workload",
        "",
        "Returns: {:,} total.".format(return_total),
    ]

    for row in return_rows:
        status = str(row.get("return_status", "Unknown"))
        count = int(row.get("total", 0) or 0)
        lines.append("- {}: {:,}".format(status, count))

    lines.extend([
        "",
        "Repairs: {:,} total.".format(repair_total),
        "- Completed: {:,}".format(completed_total),
        "- Open or not marked completed: {:,}".format(open_total),
        "- Total recorded repair cost: {}".format(
            _format_number(total_repair_cost)
        ),
        "- Recorded cost for open repairs: {}".format(
            _format_number(open_repair_cost)
        ),
    ])

    lines.extend([
        "",
        "Source: {}.".format(
            context.get("data_source", "operational database")
        ),
        "These figures are calculated from the supplied database "
        "summary. Cost values use the units stored in the database.",
    ])

    return "\n".join(lines)


def answer_question(question, operational_context):
    """Answer using operational context and locally retrieved documents."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Please enter a question.")

    if not isinstance(operational_context, dict):
        raise ValueError("Operational context must be a dictionary.")

    question_text = question.strip()

    # Exact database-derived summary: no LLM arithmetic or text merging.
    if _is_workload_question(question_text):
        return _format_workload_summary(operational_context)

    total_started = time.perf_counter()
    retrieval_started = time.perf_counter()

    try:
        retrieved_documents = search_documents(
            question_text, n_results=3
        )
    except Exception as error:
        logger.exception("Local document retrieval failed.")
        raise RuntimeError(
            "Local document retrieval failed: {}".format(error)
        ) from error

    retrieval_seconds = time.perf_counter() - retrieval_started

    serialization_started = time.perf_counter()

    operational_json = json.dumps(
        operational_context,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )

    if retrieved_documents:
        knowledge_context = "\n\n".join(
            "Document source: {source}\nDocument content:\n{text}".format(
                source=document.get("source", "unknown"),
                text=document.get("text", ""),
            )
            for document in retrieved_documents
        )
    else:
        knowledge_context = (
            "No relevant business-rule documents were retrieved. "
            "Do not invent undocumented rules."
        )

    serialization_seconds = time.perf_counter() - serialization_started

    prompt = (
        "Answer the user's question using the evidence below.\n\n"
        "VERIFIED OPERATIONAL DATABASE CONTEXT:\n"
        + operational_json
        + "\n\nRETRIEVED BUSINESS DOCUMENTS:\n"
        + knowledge_context
        + "\n\nUse the database for current facts and the retrieved "
        "documents for documented business rules. Do not invent IDs, "
        "counts, dates, or statuses. Do not treat a limited record list "
        "as a complete count. Separate verified facts from advice. "
        "Keep the answer concise, finish every sentence, and never "
        "merge unrelated numbers.\n\nUSER QUESTION:\n"
        + question_text
    )

    llm_started = time.perf_counter()

    answer = generate_response(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
    )

    logger.info(
        "Assistant timing: retrieval=%.3fs serialization=%.3fs "
        "llm_call=%.3fs total=%.3fs documents=%d prompt_chars=%d",
        retrieval_seconds,
        serialization_seconds,
        time.perf_counter() - llm_started,
        time.perf_counter() - total_started,
        len(retrieved_documents),
        len(prompt),
    )

    return answer
