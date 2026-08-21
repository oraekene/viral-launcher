from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from launcher.features import DraftFeatures
from launcher.models import GateRule
from launcher.params import ParamStore


@dataclass(frozen=True)
class RuleLine:
    rule_id: str
    verdict: str
    detail: str
    source_note: str


@dataclass(frozen=True)
class GateReport:
    verdict: str
    lines: tuple[RuleLine, ...]


RuleFn = Callable[[DraftFeatures, ParamStore], tuple[str, str]]


def _rule_length_limit(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    limit = int(store.get_float("limit.standard_chars"))
    if f.char_len > limit:
        if f.allow_premium_length:
            return "warn", f"{f.char_len} chars exceeds standard {limit}; premium length enabled"
        return "veto", f"{f.char_len} chars exceeds standard {limit}; shorten or enable premium length"
    return "pass", f"{f.char_len} chars within standard {limit}"


def _rule_length_thin(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    if f.word_count < 5:
        return "warn", f"only {f.word_count} words; too thin to elicit replies or quotes"
    return "pass", f"{f.word_count} words"


def _rule_question(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    w = store.get_float("weight.reply")
    if f.has_question or f.has_cta:
        return "pass", f"reply elicitor present (weight.reply={w})"
    return "warn", f"no question or CTA; replies weigh {w}"


def _rule_quotable(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    w = store.get_float("weight.quote")
    if f.quotable_claim:
        return "pass", f"quotable claim present (weight.quote={w})"
    return "warn", f"no quotable claim; quotes weigh {w}"


def _rule_hashtags(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    if f.hashtag_count > 3:
        return "warn", f"{f.hashtag_count} hashtags reads as spam"
    return "pass", f"{f.hashtag_count} hashtags"


def _rule_links(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    if f.link_count >= 1 and f.char_len < 100:
        return "warn", "link + short text risks low dwell; clicks weigh only 0.4"
    return "pass", "link/dwell balance ok"


def _rule_bait(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    if f.engagement_bait_hits:
        return "veto", f"engagement-bait phrasing: {', '.join(f.engagement_bait_hits)}"
    return "pass", "no engagement-bait phrasing"


def _rule_mass_reply(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    if f.mass_reply_markers:
        return "veto", f"mass-reply template markers: {', '.join(f.mass_reply_markers)}"
    return "pass", "no template markers"


def _rule_pod(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    if f.pod_signature_hits:
        return "veto", f"pod signature: {', '.join(f.pod_signature_hits)}"
    return "pass", "no pod signatures"


def _rule_mutuals(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    oon = store.get_float("oon.discount")
    boost = store.get_float("boost.bidirectional_reply")
    if f.mutuals_count is None:
        return "info", "mutuals count not provided; cannot plan follower-first engagement"
    if f.mutuals_count == 0:
        return "warn", (
            f"no mutuals pre-armed; strangers engage at x{oon} "
            f"(bidirectional reply boost +{boost} unavailable)"
        )
    return "pass", (
        f"{f.mutuals_count} mutuals can pre-arm the +{boost} bidirectional reply boost"
    )


def _rule_new_boost(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    cap = int(store.get_float("cold_start.follower_cap"))
    if f.author_followers is None:
        return "info", "follower count not provided"
    if f.author_followers <= cap:
        return "info", (
            f"account at {f.author_followers} followers qualifies for the "
            f"new-author cold-start boost (cap {cap})"
        )
    return "pass", f"account at {f.author_followers} followers (above cold-start cap {cap})"


def _rule_timing(f: DraftFeatures, store: ParamStore) -> tuple[str, str]:
    hl = int(store.get_float("half_life.minutes"))
    if f.scheduled_at is None:
        return "info", (
            f"posting immediately; stay available for the first-hour window "
            f"(~{hl} min half-life)"
        )
    return "info", (
        f"scheduled for {f.scheduled_at.isoformat()}; early engagement window still "
        f"applies (~{hl} min half-life)"
    )


RULE_FNS: dict[str, RuleFn] = {
    "negative.engagement_bait": _rule_bait,
    "negative.mass_reply_template": _rule_mass_reply,
    "negative.pod_signature": _rule_pod,
    "length.limit": _rule_length_limit,
    "length.thin": _rule_length_thin,
    "elicitation.question": _rule_question,
    "elicitation.quotable": _rule_quotable,
    "hashtags.spam": _rule_hashtags,
    "links.value": _rule_links,
    "network.mutual_plan": _rule_mutuals,
    "author.new_boost": _rule_new_boost,
    "timing.engagement_window": _rule_timing,
}


class GateEngine:
    def __init__(self, rules: list[GateRule], store: ParamStore) -> None:
        self._rules = sorted(rules, key=lambda r: r.position)
        self._store = store

    def evaluate(self, features: DraftFeatures) -> GateReport:
        lines: list[RuleLine] = []
        verdict = "passed"
        for rule in self._rules:
            if not rule.enabled:
                continue
            fn = RULE_FNS.get(rule.name)
            if fn is None:
                lines.append(
                    RuleLine(
                        rule_id=rule.name,
                        verdict="error",
                        detail="no implementation registered for this rule",
                        source_note=rule.source_note,
                    )
                )
                continue
            line_verdict, detail = fn(features, self._store)
            lines.append(
                RuleLine(
                    rule_id=rule.name,
                    verdict=line_verdict,
                    detail=detail,
                    source_note=rule.source_note,
                )
            )
            if line_verdict == "veto":
                return GateReport(verdict="vetoed", lines=tuple(lines))
            if line_verdict == "warn":
                verdict = "passed_with_warnings"
        return GateReport(verdict=verdict, lines=tuple(lines))


def load_engine(session: Session) -> GateEngine:
    rules = session.query(GateRule).order_by(GateRule.position).all()
    return GateEngine(list(rules), ParamStore(session))
