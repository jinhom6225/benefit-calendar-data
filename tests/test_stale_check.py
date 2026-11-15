"""tools/stale_check.py: window, 10-day rule, Seoul date, message file and its cap."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import stale_check  # noqa: E402

D = dt.date.fromisoformat
TODAY = D("2026-11-15")


def rnd(status, start=None, end=None, month=None, checked="2026-11-01", rid="x-2026-1"):
    return {
        "id": rid,
        "status": status,
        "start": start,
        "end": end,
        "expectedMonth": month,
        "lastChecked": checked,
    }


def stale_ids(*items, today=TODAY):
    return [i["id"] for i in stale_check.stale_items({"items": list(items)}, today)]


class StaleRuleTest(unittest.TestCase):
    def test_open_round_older_than_ten_days(self):
        self.assertEqual(stale_ids(rnd("confirmed", "2026-11-01", "2026-11-30", checked="2026-11-04")), ["x-2026-1"])

    def test_exactly_ten_days_is_fine(self):
        self.assertEqual(stale_ids(rnd("confirmed", "2026-11-01", "2026-11-30", checked="2026-11-05")), [])

    def test_partial_suspended_counts(self):
        self.assertEqual(stale_ids(rnd("partialSuspended", "2026-11-02", "2026-11-16", checked="2026-10-01")), ["x-2026-1"])

    def test_opens_within_thirty_days(self):
        self.assertEqual(stale_ids(rnd("confirmed", "2026-12-15", "2026-12-31", checked="2026-10-01")), ["x-2026-1"])

    def test_opens_after_thirty_days(self):
        self.assertEqual(stale_ids(rnd("confirmed", "2026-12-16", "2026-12-31", checked="2026-10-01")), [])

    def test_ended_yesterday_is_ignored(self):
        self.assertEqual(stale_ids(rnd("confirmed", "2026-11-01", "2026-11-14", checked="2026-10-01")), [])

    def test_closed_and_suspended_never(self):
        for status in ("closed", "suspended"):
            with self.subTest(status=status):
                self.assertEqual(stale_ids(rnd(status, "2026-11-01", "2026-11-30", checked="2026-01-01")), [])

    def test_expected_month_in_window(self):
        self.assertEqual(stale_ids(rnd("expected", month="2026-12", checked="2026-10-01")), ["x-2026-1"])
        self.assertEqual(stale_ids(rnd("expected", month="2026-11", checked="2026-10-01")), ["x-2026-1"])

    def test_expected_month_far_or_past(self):
        self.assertEqual(stale_ids(rnd("expected", month="2027-02", checked="2026-10-01")), [])
        self.assertEqual(stale_ids(rnd("expected", month="2026-10", checked="2026-10-01")), [])

    def test_real_file_today_is_clean(self):
        doc = json.loads((ROOT / "schedule.json").read_text(encoding="utf-8"))
        self.assertEqual(stale_check.stale_items(doc, TODAY), [])

    def test_real_file_late_january_flags_february_rounds(self):
        doc = json.loads((ROOT / "schedule.json").read_text(encoding="utf-8"))
        ids = [i["id"] for i in stale_check.stale_items(doc, D("2027-01-20"))]
        self.assertIn("hope2-2027-1", ids)
        self.assertIn("cultureCard-2027-1", ids)


class SeoulDateTest(unittest.TestCase):
    def test_utc_evening_is_next_seoul_day(self):
        now = dt.datetime(2026, 11, 15, 15, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(stale_check.seoul_today(now), D("2026-11-16"))

    def test_utc_morning_is_same_seoul_day(self):
        now = dt.datetime(2026, 11, 15, 1, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(stale_check.seoul_today(now), D("2026-11-15"))


class MainTest(unittest.TestCase):
    def run_main(self, items, today):
        with tempfile.TemporaryDirectory() as tmp:
            schedule = Path(tmp) / "schedule.json"
            schedule.write_text(json.dumps({"items": items}), encoding="utf-8")
            message = Path(tmp) / "message.txt"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = stale_check.main([str(schedule), "--today", today, "--message-file", str(message)])
            text = message.read_text(encoding="utf-8") if message.exists() else None
        return code, out.getvalue(), text

    def test_writes_message_when_stale(self):
        items = [
            rnd("confirmed", "2026-11-01", "2026-11-30", checked="2026-10-01", rid="a-2026-1"),
            rnd("expected", month="2026-12", checked="2026-10-01", rid="b-2026-1"),
        ]
        code, _, text = self.run_main(items, "2026-11-15")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("[신청달력] 확인 필요 2건"))
        self.assertIn("a-2026-1", text)
        self.assertIn("b-2026-1", text)

    def test_no_message_file_when_clean(self):
        code, out, text = self.run_main([rnd("closed", "2026-01-01", "2026-01-02")], "2026-11-15")
        self.assertEqual(code, 0)
        self.assertIsNone(text)
        self.assertIn("0 rounds", out)


class MessageLimitTest(unittest.TestCase):
    """The Telegram text is capped in Python by characters, never cut mid-character."""

    FOOTER = "공식 안내·지자체 공지를 확인하고 schedule.json의 lastChecked를 갱신하세요."

    def many(self, count):
        return [
            rnd("confirmed", "2026-11-01", "2026-11-30", checked="2026-10-01", rid=f"program{n:04d}-2026-1")
            for n in range(count)
        ]

    def test_short_message_unchanged(self):
        items = self.many(2)
        expected = "\n".join(
            [
                "[신청달력] 확인 필요 2건 (2026-11-15 기준)",
                "- program0000-2026-1 · confirmed · 마지막 확인 2026-10-01",
                "- program0001-2026-1 · confirmed · 마지막 확인 2026-10-01",
                self.FOOTER,
            ]
        )
        self.assertEqual(stale_check.build_message(items, TODAY), expected)

    def test_long_message_is_capped_with_tail(self):
        items = self.many(400)
        text = stale_check.build_message(items, TODAY)
        self.assertLessEqual(len(text), stale_check.MAX_MESSAGE_CHARS)
        lines = text.split("\n")
        self.assertEqual(lines[0], "[신청달력] 확인 필요 400건 (2026-11-15 기준)")
        self.assertEqual(lines[-1], self.FOOTER)
        shown = [line for line in lines if line.startswith("- ")]
        self.assertGreater(len(shown), 10)
        self.assertEqual(lines[-2], f"…외 {400 - len(shown)}건")
        # Shown lines are whole and in order.
        for n, line in enumerate(shown):
            self.assertEqual(line, f"- program{n:04d}-2026-1 · confirmed · 마지막 확인 2026-10-01")

    def test_exactly_at_limit_has_no_tail(self):
        for count in range(1, 120):
            items = self.many(count)
            text = stale_check.build_message(items, TODAY)
            with self.subTest(count=count):
                self.assertLessEqual(len(text), stale_check.MAX_MESSAGE_CHARS)
                shown = sum(1 for line in text.split("\n") if line.startswith("- "))
                if "…외 " in text:
                    self.assertLess(shown, count)
                    self.assertIn(f"…외 {count - shown}건", text)
                else:
                    self.assertEqual(shown, count)

    def test_overlong_single_line_still_capped(self):
        items = [rnd("confirmed", "2026-11-01", "2026-11-30", checked="2026-10-01", rid="가" * 5000)]
        text = stale_check.build_message(items, TODAY)
        self.assertLessEqual(len(text), stale_check.MAX_MESSAGE_CHARS)
        self.assertTrue(text.startswith("[신청달력] 확인 필요 1건"))
        self.assertTrue(text.endswith(self.FOOTER))
        self.assertIn("…외 1건", text)

    def test_written_file_is_capped_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            schedule = Path(tmp) / "schedule.json"
            schedule.write_text(json.dumps({"items": self.many(400)}), encoding="utf-8")
            message = Path(tmp) / "message.txt"
            with contextlib.redirect_stdout(io.StringIO()):
                stale_check.main([str(schedule), "--today", "2026-11-15", "--message-file", str(message)])
            text = message.read_bytes().decode("utf-8")
        self.assertLessEqual(len(text), stale_check.MAX_MESSAGE_CHARS)
        self.assertIn("…외 ", text)


class WorkflowTest(unittest.TestCase):
    def test_workflow_sends_the_file_as_is(self):
        workflow = (ROOT / ".github" / "workflows" / "stale_check.yml").read_text(encoding="utf-8")
        self.assertNotIn("head -c", workflow)
        self.assertIn('text="$(cat "${message_file}")"', workflow)


if __name__ == "__main__":
    unittest.main()
