from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from launcher.features import DraftFeatures
from launcher.models import GateRule
from launcher.params import ParamStore
from launcher.rules_seed import RULE_FNS, LineVerdict, ReportVerdict


@dataclass(frozen=True)
class RuleLine:
    rule_id: str
    verdict: LineVerdict
    detail: str
    source_note: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "verdict": self.verdict,
            "detail": self.detail,
            "source_note": self.source_note,
        }


@dataclass(frozen=True)
class GateReport:
    verdict: ReportVerdict
    lines: tuple[RuleLine, ...]


class GateEngine:
    def __init__(self, rules: list[GateRule], store: ParamStore) -> None:
        self._rules = sorted(rules, key=lambda r: r.position)
        self._store = store

    def evaluate(self, features: DraftFeatures) -> GateReport:
        lines: list[RuleLine] = []
        verdict: ReportVerdict = "passed"
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
                verdict = "vetoed"
            elif line_verdict == "warn" and verdict == "passed":
                verdict = "passed_with_warnings"
        return GateReport(verdict=verdict, lines=tuple(lines))


def load_engine(session: Session) -> GateEngine:
    rules = session.query(GateRule).order_by(GateRule.position).all()
    return GateEngine(list(rules), ParamStore(session))
