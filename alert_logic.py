"""
Alert Logic — Builder 3

Converts a RiskScore into a structured Alert with:
  - level:       Watch | Warning | Action
  - headline:    one-sentence summary
  - explanation: why this score was reached (top contributing factors)
  - actions:     recommended response steps, prioritised by level
  - sms_body:    ≤160-character string for Twilio SMS
  - voice_script: readable sentence for ElevenLabs TTS

Thresholds (per spec):
  Watch   →  score 40–60
  Warning →  score 60–80
  Action  →  score 80+

Author: Builder 3
"""

from __future__ import annotations

import datetime
import textwrap
from dataclasses import asdict, dataclass, field
from typing import Any

from risk_engine import RiskScore

# ---------------------------------------------------------------------------
# Threshold bands
# ---------------------------------------------------------------------------
THRESHOLD_WATCH   = 40.0
THRESHOLD_WARNING = 60.0
THRESHOLD_ACTION  = 80.0

# ---------------------------------------------------------------------------
# Recommended action libraries
# (each list is ordered from most urgent to least, trimmed by level)
# ---------------------------------------------------------------------------

_ACTIONS_ACTION = [
    "Activate emergency food distribution immediately at all community sites.",
    "Deploy pre-committed stock from Solana-contracted local suppliers now.",
    "Alert Second Harvest Food Bank and WFP hub — request emergency resupply.",
    "Identify and open backup supply corridors; notify transport partners.",
    "Dispatch ElevenLabs voice alerts to all registered households and farms.",
    "Coordinate with FEMA and parish emergency management for joint response.",
    "Set up distribution points at schools, churches, and community centers.",
    "Prioritise deliveries to highest food-insecurity households first.",
]

_ACTIONS_WARNING = [
    "Trigger Solana pre-commitment payments to local suppliers to lock in stock.",
    "Increase food bank inventory at community sites by at least 50%.",
    "Send ElevenLabs SMS + voice alert to registered community members.",
    "Verify all supply route statuses and identify backup options.",
    "Contact cooperative partners and smallholder farmers to confirm availability.",
    "Monitor NOAA and FEMA feeds every 2 hours for escalation signals.",
    "Prepare distribution logistics — vehicles, volunteers, site schedules.",
]

_ACTIONS_WATCH = [
    "Send informational alert to community coordinators via SMS.",
    "Review current supply node inventory levels in MongoDB dashboard.",
    "Check corridor status — confirm primary and backup routes are clear.",
    "Notify local cooperative partners of elevated risk status.",
    "Schedule a re-assessment in 6 hours using live satellite and weather feeds.",
    "Document current stock levels as baseline for escalation comparison.",
]

_ACTIONS_BY_LEVEL = {
    "Action":  _ACTIONS_ACTION,
    "Warning": _ACTIONS_WARNING,
    "Watch":   _ACTIONS_WATCH,
}

_ACTION_COUNT_BY_LEVEL = {
    "Action":  5,
    "Warning": 4,
    "Watch":   3,
}

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    alert_id: str                    # e.g. "houma-la-20260418-action"
    community_id: str
    community_name: str
    level: str                       # Watch | Warning | Action | None
    risk_score: float
    generated_at: str                # ISO timestamp
    headline: str
    explanation: str
    top_factors: list[str]
    recommended_actions: list[str]
    sms_body: str                    # ≤160 chars
    voice_script: str                # natural-language TTS script
    corridor_id: str
    data_quality: str                # full | partial | mock
    component_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _level_from_score(score: float) -> str | None:
    if score >= THRESHOLD_ACTION:
        return "Action"
    if score >= THRESHOLD_WARNING:
        return "Warning"
    if score >= THRESHOLD_WATCH:
        return "Watch"
    return None


def _headline(level: str | None, community_name: str, score: float,
              top_factors: list[str]) -> str:
    if level is None:
        return (f"{community_name}: food supply risk is currently low "
                f"(score {score:.0f}/100). No action required.")

    trigger = top_factors[0] if top_factors else "multiple risk factors"
    # Trim the trigger to a readable fragment
    trigger_short = trigger.split(":")[1].strip() if ":" in trigger else trigger
    trigger_short = trigger_short[:80]

    templates = {
        "Action":  (f"URGENT — {community_name}: Immediate food access intervention "
                    f"required (risk {score:.0f}/100). Primary concern: {trigger_short}."),
        "Warning": (f"WARNING — {community_name}: Elevated food supply risk detected "
                    f"(score {score:.0f}/100). {trigger_short}."),
        "Watch":   (f"WATCH — {community_name}: Food supply risk is rising "
                    f"(score {score:.0f}/100). Monitor closely: {trigger_short}."),
    }
    return templates[level]


def _explanation(level: str | None, score: float,
                 top_factors: list[str], data_quality: str) -> str:
    if not top_factors:
        return (f"Composite risk score: {score:.0f}/100. "
                "Insufficient signal data to identify specific factors.")

    factor_lines = "\n".join(f"  • {f}" for f in top_factors)
    quality_note = (
        " Note: some data is estimated (live APIs unavailable)."
        if data_quality == "mock" else ""
    )
    return (
        f"Risk score {score:.0f}/100 driven by:\n"
        f"{factor_lines}{quality_note}"
    )


def _sms_body(level: str | None, community_name: str,
              score: float, actions: list[str]) -> str:
    """Build an SMS ≤160 characters."""
    if level is None:
        msg = f"RootBridge: {community_name} food risk LOW ({score:.0f}/100). No action needed."
    else:
        first_action = actions[0] if actions else "Check the dashboard."
        # Shorten the action to fit
        action_fragment = first_action[:60].rstrip(" .,") + "."
        msg = f"[{level.upper()}] {community_name} risk {score:.0f}/100. {action_fragment} rootbridge.app"

    # Hard-trim to 160 chars
    return msg[:160]


def _voice_script(level: str | None, community_name: str,
                  score: float, top_factors: list[str],
                  actions: list[str]) -> str:
    """
    Natural-language script suitable for ElevenLabs TTS.
    Written to be understood by non-technical listeners.
    """
    if level is None:
        return (
            f"This is an automated message from RootBridge. "
            f"Food supply conditions in {community_name} are currently stable. "
            "No action is required at this time. We will continue monitoring."
        )

    opening = {
        "Watch":  f"This is a food supply watch notice for {community_name}.",
        "Warning":f"This is an important food supply warning for {community_name}.",
        "Action": f"Urgent message. This is an emergency food supply alert for {community_name}.",
    }[level]

    factor_text = ""
    if top_factors:
        shortened = [f.split(":")[-1].strip().lower() for f in top_factors[:2]]
        factor_text = f" The main concerns are: {', and '.join(shortened)}."

    action_text = ""
    if actions:
        action_text = f" {actions[0]}"

    closing = {
        "Watch":  " Please monitor local food supply updates and check the RootBridge dashboard.",
        "Warning":" Please take action and contact your local food coordinator.",
        "Action": " Please act immediately. Contact emergency services and your local food bank.",
    }[level]

    return opening + factor_text + action_text + closing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_alert(risk: RiskScore) -> Alert:
    """
    Convert a RiskScore into a fully structured Alert.

    Returns an Alert regardless of score — level will be None if below Watch
    threshold (score < 40), indicating no alert is needed but the record is
    still useful for audit and dashboard display.
    """
    now = datetime.datetime.utcnow()
    level = _level_from_score(risk.risk_score)

    actions = []
    if level:
        n = _ACTION_COUNT_BY_LEVEL[level]
        actions = _ACTIONS_BY_LEVEL[level][:n]

    headline    = _headline(level, risk.community_name, risk.risk_score, risk.top_factors)
    explanation = _explanation(level, risk.risk_score, risk.top_factors, risk.data_quality)
    sms         = _sms_body(level, risk.community_name, risk.risk_score, actions)
    voice       = _voice_script(level, risk.community_name, risk.risk_score,
                                 risk.top_factors, actions)

    alert_id = (
        f"{risk.community_id}-"
        f"{now.strftime('%Y%m%d')}-"
        f"{(level or 'none').lower()}"
    )

    components = risk.components
    breakdown = {
        "crop_health":          round(components.crop_health * 0.40, 2),
        "disruption":           round(components.disruption * 0.30, 2),
        "corridor_dependency":  round(components.corridor_dependency * 0.20, 2),
        "community_vulnerability": round(components.community_vulnerability * 0.10, 2),
    }

    return Alert(
        alert_id=alert_id,
        community_id=risk.community_id,
        community_name=risk.community_name,
        level=level,
        risk_score=risk.risk_score,
        generated_at=now.isoformat() + "Z",
        headline=headline,
        explanation=explanation,
        top_factors=risk.top_factors,
        recommended_actions=actions,
        sms_body=sms,
        voice_script=voice,
        corridor_id=risk.corridor_id,
        data_quality=risk.data_quality,
        component_breakdown=breakdown,
    )


def generate_all_alerts(risk_scores: list[RiskScore]) -> list[Alert]:
    """
    Generate alerts for a list of pre-computed RiskScores.
    Sorted by risk_score descending (most urgent first).
    """
    alerts = [generate_alert(r) for r in risk_scores]
    alerts.sort(key=lambda a: a.risk_score, reverse=True)
    return alerts


def filter_active_alerts(alerts: list[Alert]) -> list[Alert]:
    """Return only alerts with level Watch, Warning, or Action."""
    return [a for a in alerts if a.level is not None]