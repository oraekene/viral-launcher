from __future__ import annotations

from launcher.features import extract


def test_basic_counts() -> None:
    f = extract("Ship it. Then ship again? #build #ship #dev #code #fast")
    assert f.char_len == len("Ship it. Then ship again? #build #ship #dev #code #fast")
    assert f.question_count == 1
    assert f.has_question is True
    assert f.hashtag_count == 5


def test_link_detection() -> None:
    f = extract("Read this https://example.com/post and https://other.org")
    assert f.link_count == 2


def test_engagement_bait_hit() -> None:
    f = extract("Like if you agree. Tag someone who does this.")
    assert "like if" in f.engagement_bait_hits
    assert "tag someone" in f.engagement_bait_hits


def test_mass_reply_markers() -> None:
    f = extract("Hey {name}, quick one for you today.")
    assert "{name}" in f.mass_reply_markers


def test_pod_signature() -> None:
    f = extract("Weekly engagement pod thread, reply chain starts here.")
    assert len(f.pod_signature_hits) >= 1


def test_thread_marker() -> None:
    assert extract("1/ Why onboarding is broken\n\n2/ The fix").thread_marker is True
    assert extract("Why onboarding is broken.").thread_marker is False


def test_quotable_claim_detected() -> None:
    f = extract("Most startups do not have a marketing problem. They have a distribution habit problem.")
    assert f.quotable_claim is True


def test_quotable_claim_rejects_links_and_questions() -> None:
    assert extract("Check this out https://example.com now.").quotable_claim is False
    assert extract("Is this the best we can do?").quotable_claim is False


def test_cta_without_question_mark() -> None:
    f = extract("Tell me your worst deploy story.")
    assert f.has_cta is True
    assert f.has_question is False


def test_author_and_network_passthrough() -> None:
    f = extract("Hello world.", author_followers=800, mutuals_count=3)
    assert f.author_followers == 800
    assert f.mutuals_count == 3
