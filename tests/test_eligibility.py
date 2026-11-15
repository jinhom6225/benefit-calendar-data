"""research.md §4 table, pinned against the real schedule.json rules."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eligibility_reference import Answers, evaluate  # noqa: E402

SCHEDULE = json.loads((ROOT / "schedule.json").read_text(encoding="utf-8"))
RULES = {p["id"]: p["eligibility"] for p in SCHEDULE["programs"]}


def ans(benefits, earner=False, members=()):
    return Answers(
        benefits=None if benefits is None else frozenset(benefits),
        earner=earner,
        members=frozenset(members),
    )


# (program, benefits, earner, members, expected)
TABLE = [
    # 희망저축Ⅰ: (생계 또는 의료) + 일하는 가구원; 일 안 하면 unlikely
    ("hope1", {"livelihood"}, True, (), "likely"),
    ("hope1", {"medical"}, True, (), "likely"),
    ("hope1", {"livelihood"}, False, (), "unlikely"),
    ("hope1", {"housing"}, True, (), "unlikely"),
    ("hope1", {"nearPoor"}, True, (), "unlikely"),
    # 희망저축Ⅱ: (주거·교육·차상위) + 일하는 가구원; 생계·의료만이면 unlikely
    ("hope2", {"housing"}, True, (), "likely"),
    ("hope2", {"education"}, True, ("student",), "likely"),
    ("hope2", {"nearPoor"}, True, (), "likely"),
    ("hope2", {"livelihood", "medical"}, True, (), "unlikely"),
    ("hope2", {"housing"}, False, (), "unlikely"),
    # 교육급여: 교육 수급 + 학생; 학생은 있으나 교육 수급 아님 → check
    ("eduBenefit", {"education"}, False, ("student",), "likely"),
    ("eduBenefit", {"housing"}, True, ("student",), "check"),
    ("eduBenefit", {"nearPoor"}, False, ("student",), "check"),
    ("eduBenefit", {"education"}, True, (), "unlikely"),
    ("eduBenefit", {"livelihood"}, True, ("youth",), "unlikely"),
    # 근로·자녀장려금: 일하는 가구원 (+ 소득·재산 문장을 늘 함께 보임)
    ("eitc", {"housing"}, True, (), "likely"),
    ("eitc", {"nearPoor"}, True, ("student",), "likely"),
    ("eitc", {"livelihood"}, False, (), "unlikely"),
    # 청년내일: (수급·차상위) + 청년 + 일하는 가구원; 청년은 있으나 일 안 함 → check
    ("youthSaving", {"livelihood"}, True, ("youth",), "likely"),
    ("youthSaving", {"nearPoor"}, True, ("youth",), "likely"),
    ("youthSaving", {"housing"}, False, ("youth",), "check"),
    ("youthSaving", {"education"}, True, (), "unlikely"),
    ("youthSaving", {"housing"}, True, ("student",), "unlikely"),
    # 에너지바우처: (생계·의료·주거·교육) + 취약 가구원; 수급인데 해당 가구원 없음 → check
    ("energyVoucher", {"livelihood"}, False, ("vulnerable",), "likely"),
    ("energyVoucher", {"housing"}, True, ("vulnerable",), "likely"),
    ("energyVoucher", {"education"}, False, (), "check"),
    ("energyVoucher", {"medical"}, False, ("student",), "check"),
    ("energyVoucher", {"nearPoor"}, False, ("vulnerable",), "unlikely"),
    # 문화누리: 수급 아무거나 또는 차상위
    ("cultureCard", {"livelihood"}, False, (), "likely"),
    ("cultureCard", {"nearPoor"}, False, (), "likely"),
    ("cultureCard", {"education"}, True, ("student",), "likely"),
]


class EligibilityTableTest(unittest.TestCase):
    def test_table_rows(self):
        self.assertGreaterEqual(len(TABLE), 30)
        for program, benefits, earner, members, expected in TABLE:
            with self.subTest(program=program, benefits=sorted(benefits), earner=earner, members=members):
                self.assertEqual(evaluate(RULES[program], ans(benefits, earner, members)), expected)

    def test_skipped_or_unknown_is_check_everywhere(self):
        for program, rule in RULES.items():
            with self.subTest(program=program):
                self.assertEqual(evaluate(rule, ans(None, True, ("youth",))), "check")
                self.assertEqual(evaluate(rule, ans(set(), False)), "check")

    def test_r1_scene_kim(self):
        # research §14-2 R1: 주거급여 · 일함 · 고등학생 자녀 → likely 3, check 2.
        kim = ans({"housing"}, True, ("student",))
        results = {pid: evaluate(rule, kim) for pid, rule in RULES.items()}
        likely = sorted(p for p, r in results.items() if r == "likely")
        check = sorted(p for p, r in results.items() if r == "check")
        self.assertEqual(likely, ["cultureCard", "eitc", "hope2"])
        self.assertEqual(check, ["eduBenefit", "energyVoucher"])

    def test_unanswered_question_lowers_to_check_only(self):
        # App rule 2026-11-15: unanswered (None) question 2/3 never hides a program.
        rules = RULES
        answers = Answers(frozenset({"housing"}), earner=None, members=None)
        # Benefit condition met, only unanswered conditions missing -> check.
        for pid in ("hope2", "youthSaving", "energyVoucher", "eduBenefit"):
            self.assertEqual(evaluate(rules[pid], answers), "check", pid)
        # A miss on the answered benefit question still hides the program.
        self.assertEqual(evaluate(rules["hope1"], answers), "unlikely")
        answered_no = Answers(frozenset({"housing"}), earner=False, members=frozenset())
        self.assertEqual(evaluate(rules["hope2"], answered_no), "unlikely")

    def test_max_result_caps_likely(self):
        rule = {"anyBenefit": [], "needsEarner": True, "anyMember": [], "maxResult": "check"}
        self.assertEqual(evaluate(rule, ans({"housing"}, True)), "check")
        self.assertEqual(evaluate(rule, ans({"housing"}, False)), "unlikely")

    def test_eitc_always_shows_its_note(self):
        self.assertIs(RULES["eitc"].get("alwaysShowNote"), True)
        self.assertTrue(RULES["eitc"]["checkNote"])

    def test_every_program_has_a_rule(self):
        self.assertEqual(
            sorted(RULES),
            sorted(["hope1", "hope2", "eduBenefit", "eitc", "youthSaving", "energyVoucher", "cultureCard"]),
        )


if __name__ == "__main__":
    unittest.main()
