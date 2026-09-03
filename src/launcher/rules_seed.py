from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Literal, NamedTuple

from sqlalchemy.orm import Session

from launcher.features import DraftFeatures
from launcher.models import GateRule
from launcher.params import ParamStore

LineVerdict = Literal["pass", "warn", "veto", "info", "error"]
ReportVerdict = Literal["passed", "passed_with_warnings", "vetoed"]

RuleFn = Callable[[DraftFeatures, ParamStore], tuple[LineVerdict, str]]


def _rule_bait(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    if f.engagement_bait_hits:
        return "veto", f"engagement-bait phrasing: {', '.join(f.engagement_bait_hits)}"
    return "pass", "no engagement-bait phrasing"


def _rule_mass_reply(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    if f.mass_reply_markers:
        return "veto", f"mass-reply template markers: {', '.join(f.mass_reply_markers)}"
    return "pass", "no template markers"


def _rule_pod(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    if f.pod_signature_hits:
        return "veto", f"pod signature: {', '.join(f.pod_signature_hits)}"
    return "pass", "no pod signatures"


def _rule_length_limit(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    limit = int(store.get_float("limit.standard_chars"))
    if f.char_len > limit:
        if f.allow_premium_length:
            return "warn", f"{f.char_len} chars exceeds standard {limit}; premium length enabled"
        return "veto", f"{f.char_len} chars exceeds standard {limit}; shorten or enable premium length"
    return "pass", f"{f.char_len} chars within standard {limit}"


def _rule_length_thin(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    if f.word_count < 5:
        return "warn", f"only {f.word_count} words; too thin to elicit replies or quotes"
    return "pass", f"{f.word_count} words"


def _rule_question(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    w = store.get_float("weight.reply")
    if f.has_question or f.has_cta:
        return "pass", f"reply elicitor present (weight.reply={w})"
    return "warn", f"no question or CTA; replies weigh {w}"


def _rule_quotable(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    w = store.get_float("weight.quote")
    if f.quotable_claim:
        return "pass", f"quotable claim present (weight.quote={w})"
    return "warn", f"no quotable claim; quotes weigh {w}"


def _rule_hashtags(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    if f.hashtag_count > 3:
        return "warn", f"{f.hashtag_count} hashtags reads as spam"
    return "pass", f"{f.hashtag_count} hashtags"


def _rule_links(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    w_click = store.get_float("weight.click")
    if f.link_count >= 1 and f.char_len < 100:
        return "warn", f"link + short text risks low dwell; clicks weigh only {w_click}"
    return "pass", "link/dwell balance ok"


def _rule_mutuals(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
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


def _rule_new_boost(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    cap = int(store.get_float("cold_start.follower_cap"))
    decay = store.get_float("author.diversity_decay")
    floor = store.get_float("author.diversity_floor")
    diversity_note = (
        f"same-author streaks decay x{decay} (floor {floor}); vary sources"
    )
    if f.author_followers is None:
        return "info", f"follower count not provided; {diversity_note}"
    if f.author_followers <= cap:
        return "info", (
            f"account at {f.author_followers} followers qualifies for the "
            f"new-author cold-start boost (cap {cap}); {diversity_note}"
        )
    return "pass", (
        f"account at {f.author_followers} followers (above cold-start cap {cap}); "
        f"{diversity_note}"
    )


def _rule_timing(f: DraftFeatures, store: ParamStore) -> tuple[LineVerdict, str]:
    hl = int(store.get_float("half_life.minutes"))
    age_h = store.get_float("age_filter.hours")
    if f.scheduled_at is not None:
        scheduled = f.scheduled_at
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        delta_h = (scheduled - datetime.now(timezone.utc)).total_seconds() / 3600
        if delta_h > age_h:
            return "warn", (
                f"scheduled {delta_h:.0f}h out; posts older than {int(age_h)}h stop "
                f"being served (AgeFilter)"
            )
        return "info", (
            f"scheduled for {f.scheduled_at.isoformat()}; early engagement window "
            f"still applies (~{hl} min half-life)"
        )
    return "info", (
        f"posting immediately; stay available for the first-hour window "
        f"(~{hl} min half-life)"
    )


class RuleSpec(NamedTuple):
    name: str
    fn: RuleFn
    param_ref: str | None
    source_note: str


RULE_SEED: tuple[RuleSpec, ...] = (
    RuleSpec(
        "negative.engagement_bait",
        _rule_bait,
        None,
        "X anti-gaming systems (bdsm inauthentic-engagement labeling); downside is report -234 / not-interested -43.2",
    ),
    RuleSpec(
        "negative.mass_reply_template",
        _rule_mass_reply,
        None,
        "X botmaker/scarecrow automation labels; mass-similar-reply detection",
    ),
    RuleSpec(
        "negative.pod_signature",
        _rule_pod,
        None,
        "bdsm engagement-pod detection; coordinated inauthentic behavior",
    ),
    RuleSpec(
        "length.limit",
        _rule_length_limit,
        "limit.standard_chars",
        "X standard post limit 280 chars; premium tiers allow longer",
    ),
    RuleSpec(
        "length.thin",
        _rule_length_thin,
        None,
        "Too little content to elicit weighted actions (reply 5.0, quote 5.0)",
    ),
    RuleSpec(
        "elicitation.question",
        _rule_question,
        "weight.reply",
        "Replies weigh 5.0 (assumed x-algorithm production weight, Aug 13 2026)",
    ),
    RuleSpec(
        "elicitation.quotable",
        _rule_quotable,
        "weight.quote",
        "Quotes weigh 5.0 (assumed x-algorithm production weight, Aug 13 2026)",
    ),
    RuleSpec(
        "hashtags.spam",
        _rule_hashtags,
        "oon.discount",
        "Spam signals depress reach; out-of-network factor is 0.75",
    ),
    RuleSpec(
        "links.value",
        _rule_links,
        "weight.click",
        "External links risk low dwell; clicks weigh 0.4 (assumed production weight)",
    ),
    RuleSpec(
        "network.mutual_plan",
        _rule_mutuals,
        "boost.bidirectional_reply",
        "Bidirectional-follow reply boost +15; out-of-network discount x0.75",
    ),
    RuleSpec(
        "author.new_boost",
        _rule_new_boost,
        "cold_start.follower_cap",
        "New-author cold-start boost at <=1000 followers; author diversity decay x0.5 floor 0.25",
    ),
    RuleSpec(
        "timing.engagement_window",
        _rule_timing,
        "half_life.minutes",
        "Median half-life ~80 min (arXiv:2302.09654); AgeFilter stops serving posts after 48h",
    ),
)

RULE_FNS: dict[str, RuleFn] = {spec.name: spec.fn for spec in RULE_SEED}


def seed_rules(session: Session) -> None:
    existing = {r.name for r in session.query(GateRule).all()}
    for pos, spec in enumerate(RULE_SEED):
        if spec.name in existing:
            continue
        session.add(
            GateRule(
                name=spec.name,
                position=pos,
                param_ref=spec.param_ref,
                source_note=spec.source_note,
                enabled=True,
            )
        )
