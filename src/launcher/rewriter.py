from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from launcher.config import Settings
from launcher.cost import BudgetExceeded, CostMeter
from launcher.features import extract
from launcher.gate import load_engine
from launcher.models import Draft, DraftVariant
from launcher.params import ParamStore
from launcher.scoring import resolve_score


@dataclass(frozen=True)
class GenerationResult:
    texts: tuple[str, ...]
    usd: float
    tokens_in: int
    tokens_out: int


class VariantProvider(Protocol):
    def generate(self, draft_text: str, n: int) -> GenerationResult: ...

    def estimate_cost(self, draft_text: str, n: int) -> float: ...


class ProviderError(RuntimeError):
    pass


def default_provider(settings: Settings, store: ParamStore) -> VariantProvider:
    if settings.llm_api_key:
        return OpenAICompatProvider(settings, store)
    return HeuristicProvider()


FILLER_WORDS: tuple[str, ...] = (
    "just",
    "really",
    "very",
    "actually",
    "basically",
    "literally",
    "simply",
)

_HEDGE_RE = re.compile(
    r"\b(?:i think|i believe|kind of|sort of|maybe|perhaps)\b[,\s]*", re.IGNORECASE
)
_MULTI_SPACE_RE = re.compile(r"\s+")


class HeuristicProvider:
    def generate(self, draft_text: str, n: int) -> GenerationResult:
        seen: list[str] = []
        for candidate in self._transforms(draft_text):
            stripped = candidate.strip()
            if stripped and stripped != draft_text and stripped not in seen:
                seen.append(stripped)
            if len(seen) >= n:
                break
        return GenerationResult(texts=tuple(seen), usd=0.0, tokens_in=0, tokens_out=0)

    def estimate_cost(self, draft_text: str, n: int) -> float:
        return 0.0

    def _transforms(self, text: str) -> list[str]:
        return [
            self._tighten(text),
            self._frontload(text),
            self._add_question(text),
            self._claim_only(text),
            self._strip_hedges(text),
        ]

    def _tighten(self, text: str) -> str:
        words = [
            w for w in text.split() if w.lower().strip(".,!?") not in FILLER_WORDS
        ]
        return _MULTI_SPACE_RE.sub(" ", " ".join(words)).strip()

    def _frontload(self, text: str) -> str:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if len(sentences) < 2:
            return text
        longest = max(sentences, key=len)
        reordered = [longest] + [s for s in sentences if s != longest]
        return " ".join(reordered)

    def _add_question(self, text: str) -> str:
        if "?" in text:
            return text
        return f"{text.rstrip()}\n\nWhat would you add?"

    def _claim_only(self, text: str) -> str:
        first = re.split(r"(?<=[.!?])\s+|\n\n", text.strip())[0].strip()
        return first if first.endswith((".", "!", "?")) else f"{first}."

    def _strip_hedges(self, text: str) -> str:
        cleaned = _HEDGE_RE.sub("", text)
        return _MULTI_SPACE_RE.sub(" ", cleaned).strip()


class OpenAICompatProvider:
    def __init__(self, settings: Settings, store: ParamStore) -> None:
        self._settings = settings
        self._store = store

    def generate(self, draft_text: str, n: int) -> GenerationResult:
        system = (
            "You rewrite short social posts. Given a draft, produce exactly "
            f"{n} improved variants, one per line, each prefixed with '- '. "
            "Preserve the author's meaning; sharpen the hook; invite replies "
            "or quotes honestly. Never add engagement bait like 'like if' or "
            "'tag someone'."
        )
        try:
            resp = httpx.post(
                f"{self._settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": draft_text},
                    ],
                    "n": 1,
                    "temperature": 0.8,
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"llm request failed: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"llm returned status {resp.status_code}: {resp.text}")
        payload = resp.json()
        content: str = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage", {})
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        texts = self._parse_texts(content)
        if len(texts) < n:
            top_up = httpx.post(
                f"{self._settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": (
                                f"{draft_text}\n\nProduce {n - len(texts)} more "
                                "variants, same format."
                            ),
                        },
                    ],
                    "n": 1,
                    "temperature": 1.0,
                },
                timeout=30.0,
            )
            if top_up.status_code == 200:
                top_payload = top_up.json()
                top_usage = top_payload.get("usage", {})
                tokens_in += int(top_usage.get("prompt_tokens", 0))
                tokens_out += int(top_usage.get("completion_tokens", 0))
                merged = [*texts, *self._parse_texts(
                    top_payload["choices"][0]["message"]["content"]
                )]
                deduped: list[str] = []
                for t in merged:
                    if t not in deduped:
                        deduped.append(t)
                texts = tuple(deduped[:n])
        usd = self._cost_usd(tokens_in, tokens_out)
        return GenerationResult(
            texts=texts, usd=usd, tokens_in=tokens_in, tokens_out=tokens_out
        )

    @staticmethod
    def _parse_texts(content: str) -> tuple[str, ...]:
        return tuple(
            line.lstrip("- ").strip()
            for line in content.splitlines()
            if line.strip().startswith("-")
        )

    def _cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        p_in = self._store.get_float("llm.price_input_per_1k_usd")
        p_out = self._store.get_float("llm.price_output_per_1k_usd")
        return tokens_in / 1000.0 * p_in + tokens_out / 1000.0 * p_out

    def estimate_cost(self, draft_text: str, n: int) -> float:
        est_tokens_in = max(int(len(draft_text) / 4), 1) + 60
        est_tokens_out = n * 80
        return self._cost_usd(est_tokens_in, est_tokens_out)


@dataclass(frozen=True)
class RankedVariant:
    id: int
    text: str
    score: float
    reasons: tuple[str, ...]
    gate_lines: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class RewriteResult:
    draft_id: int
    top: tuple[RankedVariant, ...]
    generated: int
    vetoed_count: int
    cost_usd: float


def rank_candidates(
    texts: Sequence[str],
    scores: Sequence[float],
    vetoed: Sequence[bool],
    *,
    limit: int = 3,
) -> list[int]:
    """Pure ranking policy: indices of the top non-vetoed candidates by
    score, highest first; stable on ties."""
    order = sorted(
        (i for i in range(len(texts)) if not vetoed[i]),
        key=lambda i: scores[i],
        reverse=True,
    )
    return order[:limit]


def rewrite_flow(
    session: Session,
    draft_id: int,
    provider: VariantProvider,
    n: int | None = None,
) -> RewriteResult:
    store = ParamStore(session)
    meter = CostMeter(session)
    cap = store.get_float("cost.per_draft_cap_usd")
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"draft {draft_id} not found")

    if n is None:
        n = int(store.get_float("rewriter.default_n"))
    projected_spend = meter.spent(draft_id) + provider.estimate_cost(draft.text, n)
    if projected_spend > cap + 1e-9:
        raise BudgetExceeded(
            f"draft {draft_id} projected spend ${projected_spend:.4f} exceeds "
            f"the ${cap:.4f} per-draft cap"
        )
    gen = provider.generate(draft.text, n)
    per_variant_cost = gen.usd / max(len(gen.texts), 1)

    engine = load_engine(session)
    candidates = list(gen.texts)
    rows: list[DraftVariant] = []
    scores: list[float] = []
    vetoes: list[bool] = []
    vetoed_count = 0

    for idx, text in enumerate(candidates):
        features = extract(
            text,
            author_followers=draft.author_followers,
            mutuals_count=draft.mutuals_count,
            allow_premium_length=draft.allow_premium_length,
        )
        report = engine.evaluate(features)
        vetoed = report.verdict == "vetoed"
        vetoed_count += int(vetoed)
        score = 0.0
        reasons: list[str] = []
        kind = "interim"
        if not vetoed:
            scored = resolve_score(session, draft.project_id, features, text)
            score = scored.score
            reasons = scored.reasons
            kind = scored.kind
        row = DraftVariant(
            draft_id=draft_id,
            text=text,
            variant_index=idx,
            score=score,
            score_kind=kind,
            reasons=reasons,
            gate_lines=[line.as_dict() for line in report.lines],
            vetoed=vetoed,
            llm_cost_usd=round(per_variant_cost, 6),
        )
        session.add(row)
        session.flush()
        rows.append(row)
        scores.append(score)
        vetoes.append(vetoed)

    meter.record(
        draft_id,
        kind="llm" if gen.usd > 0 else "heuristic",
        usd=gen.usd,
        tokens_in=gen.tokens_in,
        tokens_out=gen.tokens_out,
        note=f"{len(gen.texts)} variants generated",
    )

    top = tuple(
        RankedVariant(
            id=rows[i].id,
            text=rows[i].text,
            score=rows[i].score,
            reasons=tuple(rows[i].reasons),
            gate_lines=tuple(rows[i].gate_lines or ()),
        )
        for i in rank_candidates(candidates, scores, vetoes)
    )
    return RewriteResult(
        draft_id=draft_id,
        top=top,
        generated=len(gen.texts),
        vetoed_count=vetoed_count,
        cost_usd=gen.usd,
    )


@dataclass(frozen=True)
class RewriteAttempt:
    """Budget policy next to the rewrite service call: success carries the
    result, a blown per-draft cap carries the error instead of raising."""

    result: RewriteResult | None
    error: str | None


def try_rewrite_flow(
    session: Session,
    draft_id: int,
    provider: VariantProvider,
    n: int | None = None,
) -> RewriteAttempt:
    try:
        return RewriteAttempt(result=rewrite_flow(session, draft_id, provider, n), error=None)
    except BudgetExceeded as exc:
        return RewriteAttempt(result=None, error=str(exc))
