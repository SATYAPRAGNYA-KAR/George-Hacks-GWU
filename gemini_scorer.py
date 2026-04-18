"""
Gemini Flash 2.5 risk scorer — Builder 3

Replaces the deterministic formula with an LLM-based score.
Falls back to the weighted formula if the API is down or parsing fails.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Simple in-process cache: (region, inputs_hash) → result dict
_score_cache: dict[str, dict] = {}


def _inputs_hash(crop_payload: dict, disruption_payload: dict, corridor: dict, community: dict) -> str:
    blob = json.dumps([crop_payload, disruption_payload, corridor, community], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _build_prompt(
    community_id: str,
    community_name: str,
    crop_payload: dict,
    disruption_payload: dict,
    corridor: dict,
    community: dict,
) -> str:
    return f"""You are a food security risk analyst. Score the food supply risk for a Louisiana community.

## Community
- ID: {community_id}
- Name: {community_name}
- Food insecurity rate: {community.get('food_insecurity_rate', 'unknown')}
- Corridor dependency weight: {community.get('dependency_weight', 'unknown')}

## Crop Health Data (from NASA LANCE/MODIS)
{json.dumps(crop_payload.get('summary', crop_payload), indent=2)}

## Supply Disruptions (NOAA + FEMA + Routes)
{json.dumps({k: v for k, v in disruption_payload.items() if k != '_mock'}, indent=2)}

## Supply Corridor
- ID: {corridor.get('id')}
- Name: {corridor.get('name')}
- Crops: {corridor.get('crop_types')}

## Your Task
Return ONLY a JSON object — no markdown, no explanation — with exactly this schema:
{{
  "risk_score": <integer 0-100>,
  "top_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "reasoning": "<2-3 sentence explanation>"
}}

Scoring guide:
- 0–39: Low risk, supply stable
- 40–59: Watch — early stress signals
- 60–79: Warning — significant disruption likely
- 80–100: Action — immediate intervention needed

Weight your judgment: crop health (40%), disruptions (30%), corridor dependency (20%), community vulnerability (10%)."""


def score_risk_llm(
    community_id: str,
    community_name: str,
    crop_payload: dict,
    disruption_payload: dict,
    corridor: dict,
    community: dict,
) -> dict[str, Any] | None:
    """
    Call Gemini Flash 2.5 to score risk. Returns parsed dict or None on failure.
    Caches by (community_id, inputs_hash).
    """
    cache_key = f"{community_id}:{_inputs_hash(crop_payload, disruption_payload, corridor, community)}"
    if cache_key in _score_cache:
        logger.debug("Cache hit for %s", community_id)
        return _score_cache[cache_key]

    prompt = _build_prompt(
        community_id, community_name,
        crop_payload, disruption_payload,
        corridor, community,
    )

    try:
        response = _client.models.generate_content(
            model="gemini-2.5-flash-preview-05-20",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,       # low temp = consistent scoring
                max_output_tokens=512,
            ),
        )
        raw = response.text.strip()

        # Strip markdown fences if the model adds them anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)

        # Validate schema
        assert isinstance(result["risk_score"], (int, float))
        assert isinstance(result["top_factors"], list)
        assert isinstance(result["reasoning"], str)

        result["risk_score"] = max(0, min(100, float(result["risk_score"])))
        result["_source"] = "gemini"

        _score_cache[cache_key] = result
        return result

    except Exception as e:
        logger.warning("Gemini scoring failed for %s: %s", community_id, e)
        return None