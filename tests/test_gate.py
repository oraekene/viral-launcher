from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.gate import GateEngine, load_engine
from launcher.params import seed_params
from launcher.rules_seed import RULE_SEED, seed_rules


@pytest.fixture()
def engine(session: Session) -> GateEngine:
    seed_params(session)
    seed_rules(session)
    session.commit()
    return load_engine(session)


CLEAN_DRAFT = (
    "We cut our release cycle from 14 days to 2 by deleting half the checklist. "
    "Speed was never the constraint. Fear was.\n\nWhat would you add?"
)


def test_clean_draft_passes(engine: GateEngine) -> None:
    f = extract(CLEAN_DRAFT, author_followers=5000, mutuals_count=12)
    report = engine.evaluate(f)
    assert report.verdict == "passed"
    assert all(line.verdict != "veto" for line in report.lines)


def test_every_line_names_its_source(engine: GateEngine) -> None:
    f = extract(CLEAN_DRAFT)
    report = engine.evaluate(f)
    assert len(report.lines) > 0
    for line in report.lines:
        assert line.source_note, f"rule {line.rule_id} has empty source note"


def test_engagement_bait_is_hard_veto(engine: GateEngine) -> None:
    f = extract("Like if you agree! Tag someone who needs this.")
    report = engine.evaluate(f)
    assert report.verdict == "vetoed"
    assert report.lines[0].rule_id == "negative.engagement_bait"


def test_mass_reply_template_is_hard_veto(engine: GateEngine) -> None:
    f = extract("Hey {name}, dm me your biggest struggle right now.")
    report = engine.evaluate(f)
    assert report.verdict == "vetoed"
    vetoes = [l for l in report.lines if l.verdict == "veto"]
    assert any(l.rule_id == "negative.mass_reply_template" for l in vetoes)
    assert all(
        l.verdict != "veto"
        for l in report.lines
        if l.rule_id == "negative.engagement_bait"
    )


def test_pod_signature_is_hard_veto(engine: GateEngine) -> None:
    f = extract("Engagement pod roll call. Reply chain below.")
    report = engine.evaluate(f)
    assert report.verdict == "vetoed"
    vetoes = [l for l in report.lines if l.verdict == "veto"]
    assert any(l.rule_id == "negative.pod_signature" for l in vetoes)


def test_first_veto_preserves_verdict_while_evaluating_all_rules(
    engine: GateEngine,
) -> None:
    long_bait = ("Like if you agree! " + "x" * 300)
    f = extract(long_bait)
    report = engine.evaluate(f)
    assert report.verdict == "vetoed"
    assert len(report.lines) > 1
    assert report.lines[0].rule_id == "negative.engagement_bait"
    assert report.lines[0].verdict == "veto"


def test_vetoed_report_still_contains_advisory_lines(engine: GateEngine) -> None:
    long_bait = ("Like if you agree! " + "x" * 300)
    f = extract(long_bait)
    report = engine.evaluate(f)
    assert report.verdict == "vetoed"
    rule_ids = [line.rule_id for line in report.lines]
    assert rule_ids[0] == "negative.engagement_bait"
    for expected in (
        "elicitation.question",
        "elicitation.quotable",
        "network.mutual_plan",
        "author.new_boost",
        "timing.engagement_window",
    ):
        assert expected in rule_ids


def test_missing_elicitation_warns(engine: GateEngine) -> None:
    f = extract("https://example.com")
    report = engine.evaluate(f)
    assert report.verdict == "passed_with_warnings"
    rule_ids = {line.rule_id for line in report.lines if line.verdict == "warn"}
    assert "elicitation.question" in rule_ids
    assert "elicitation.quotable" in rule_ids
    assert "length.thin" in rule_ids


def test_overlong_draft_vetoed_unless_premium(engine: GateEngine) -> None:
    body = "Sentence one is here. " + "Another sentence follows. " * 12
    f = extract(body)
    assert engine.evaluate(f).verdict == "vetoed"
    premium = extract(body, allow_premium_length=True)
    assert engine.evaluate(premium).verdict != "vetoed"


def test_hashtag_spam_warns(engine: GateEngine) -> None:
    f = extract("Big news today #a #b #c #d #e")
    report = engine.evaluate(f)
    warns = {line.rule_id for line in report.lines if line.verdict == "warn"}
    assert "hashtags.spam" in warns


def test_link_plus_short_text_warns(engine: GateEngine) -> None:
    f = extract("This changed everything https://example.com")
    report = engine.evaluate(f)
    warns = {line.rule_id for line in report.lines if line.verdict == "warn"}
    assert "links.value" in warns


def test_no_mutuals_warns_about_oon_discount(engine: GateEngine) -> None:
    f = extract(CLEAN_DRAFT, mutuals_count=0)
    report = engine.evaluate(f)
    warn_lines = [l for l in report.lines if l.rule_id == "network.mutual_plan"]
    assert warn_lines and warn_lines[0].verdict == "warn"
    assert "0.75" in warn_lines[0].detail


def test_new_author_boost_info(engine: GateEngine) -> None:
    f = extract(CLEAN_DRAFT, author_followers=800)
    report = engine.evaluate(f)
    boost = [l for l in report.lines if l.rule_id == "author.new_boost"]
    assert boost and boost[0].verdict == "info"
    assert "1000" in boost[0].detail


def test_disabled_rule_is_skipped(session: Session, engine: GateEngine) -> None:
    from launcher.models import GateRule

    rule = session.query(GateRule).filter_by(name="elicitation.question").one()
    rule.enabled = False
    session.commit()

    fresh_engine = load_engine(session)
    f = extract("Plain statement with no question at all here.")
    report = fresh_engine.evaluate(f)
    assert all(l.rule_id != "elicitation.question" for l in report.lines)


def test_rule_seed_covers_negatives_first() -> None:
    assert RULE_SEED[0].name.startswith("negative.")
