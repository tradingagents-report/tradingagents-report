"""Analyst-owned directional signals for the compact decision brief."""

from __future__ import annotations

import logging
from typing import Any

from tradingagents.agents.schemas import DecisionStance, SectionSignal
from tradingagents.agents.utils.agent_utils import get_language_instruction

logger = logging.getLogger(__name__)


def unavailable_section_signal(agent_name: str) -> dict[str, str]:
    """Return an explicit fallback without guessing direction from prose."""
    return {
        "stance": DecisionStance.UNAVAILABLE.value,
        "note": f"{agent_name} did not produce a structured signal.",
    }


def extract_section_signal(
    structured_llm: Any | None,
    report: str,
    agent_name: str,
) -> dict[str, str]:
    """Compress one completed analyst report into its own typed signal."""
    if not report.strip() or structured_llm is None:
        return unavailable_section_signal(agent_name)

    from tradingagents.dataflows.config import get_config

    language = get_config().get("output_language", "English")
    language_line = (
        f"Write the note entirely in {language}."
        if str(language).strip().lower() != "english"
        else "Write the note in English."
    )
    prompt = f"""You are the {agent_name}. Convert your completed report below into one machine-readable section signal.

Choose exactly one stance: bullish, neutral, bearish, or unavailable. Use unavailable only when the report contains no usable directional evidence. The note must be one concise evidence-based sentence. {language_line} Do not leave the note in a different language than the configured report language, even if the report mixes languages. Do not infer facts that are absent from the report.{get_language_instruction()}

Completed report:
{report}"""
    try:
        result = structured_llm.invoke(prompt)
        signal = (
            result
            if isinstance(result, SectionSignal)
            else SectionSignal.model_validate(result)
        )
        return signal.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - signal failure must not fail analysis
        logger.warning("%s signal extraction failed: %s", agent_name, exc)
        return unavailable_section_signal(agent_name)
