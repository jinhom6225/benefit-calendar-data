"""Reference evaluator for programs[].eligibility (README "자격 규칙").

The app implements the same rules in Dart (research.md §4, plan P3). This copy
exists so tests can pin the documented semantics against the real
schedule.json. Results: "likely" (해당될 수 있어요), "check" (조건을
확인하세요), "unlikely" (숨김).
"""

from __future__ import annotations

from dataclasses import dataclass, field

RECIPIENT_BENEFITS = frozenset({"livelihood", "medical", "housing", "education"})


@dataclass(frozen=True)
class Answers:
    # None = skipped or "없음/모름"; otherwise the chosen benefit codes.
    benefits: frozenset[str] | None
    # None = question 2 / 3 not answered (app 2026-11-15: an unanswered
    # question can only lower a result to "check", never to "unlikely").
    earner: bool | None = False
    members: frozenset[str] | None = field(default_factory=frozenset)


def expand_benefits(codes: list[str]) -> frozenset[str]:
    expanded = set(codes)
    if "anyRecipient" in expanded:
        expanded.discard("anyRecipient")
        expanded |= RECIPIENT_BENEFITS
    return frozenset(expanded)


def evaluate(rule: dict, answers: Answers) -> str:
    if not answers.benefits:
        return "check"
    misses = []
    unknown = set()
    wanted = expand_benefits(rule.get("anyBenefit", []))
    if wanted and not (answers.benefits & wanted):
        misses.append("benefit")
    if rule.get("needsEarner") and not answers.earner:
        misses.append("earner")
        if answers.earner is None:
            unknown.add("earner")
    members = frozenset(rule.get("anyMember", []))
    if members and not ((answers.members or frozenset()) & members):
        misses.append("member")
        if answers.members is None:
            unknown.add("member")
    soft = frozenset(rule.get("softMiss", [])) | unknown
    if any(miss not in soft for miss in misses):
        return "unlikely"
    result = "check" if misses else "likely"
    if result == "likely" and rule.get("maxResult") == "check":
        result = "check"
    return result
