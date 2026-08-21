from __future__ import annotations

from typing import NamedTuple

from sqlalchemy.orm import Session

from launcher.models import GateRule


class RuleSpec(NamedTuple):
    name: str
    param_ref: str | None
    source_note: str


RULE_SEED: tuple[RuleSpec, ...] = (
    RuleSpec(
        "negative.engagement_bait",
        None,
        "X anti-gaming systems (bdsm inauthentic-engagement labeling); downside is report -234 / not-interested -43.2",
    ),
    RuleSpec(
        "negative.mass_reply_template",
        None,
        "X botmaker/scarecrow automation labels; mass-similar-reply detection",
    ),
    RuleSpec(
        "negative.pod_signature",
        None,
        "bdsm engagement-pod detection; coordinated inauthentic behavior",
    ),
    RuleSpec(
        "length.limit",
        "limit.standard_chars",
        "X standard post limit 280 chars; premium tiers allow longer",
    ),
    RuleSpec(
        "length.thin",
        None,
        "Too little content to elicit weighted actions (reply 5.0, quote 5.0)",
    ),
    RuleSpec(
        "elicitation.question",
        "weight.reply",
        "Replies weigh 5.0 in x-algorithm production params (Aug 13 2026)",
    ),
    RuleSpec(
        "elicitation.quotable",
        "weight.quote",
        "Quotes weigh 5.0 in x-algorithm production params (Aug 13 2026)",
    ),
    RuleSpec(
        "hashtags.spam",
        "oon.discount",
        "Spam signals depress reach; out-of-network factor is 0.75",
    ),
    RuleSpec(
        "links.value",
        "weight.click",
        "External links risk low dwell; clicks weigh only 0.4",
    ),
    RuleSpec(
        "network.mutual_plan",
        "boost.bidirectional_reply",
        "Bidirectional-follow reply boost +15; out-of-network discount x0.75",
    ),
    RuleSpec(
        "author.new_boost",
        "cold_start.follower_cap",
        "New-author cold-start boost applies at <=1000 followers (ColdStartFollowerCap)",
    ),
    RuleSpec(
        "timing.engagement_window",
        "half_life.minutes",
        "Median half-life ~80 min (arXiv:2302.09654); the first hour decides",
    ),
)


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
