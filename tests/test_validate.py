"""tools/validate.py: every rule has a failing case, and the real file passes."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import validate  # noqa: E402

REAL = json.loads((ROOT / "schedule.json").read_text(encoding="utf-8"))


def doc():
    return copy.deepcopy(REAL)


def item(d, item_id):
    return next(i for i in d["items"] if i["id"] == item_id)


def program(d, program_id):
    return next(p for p in d["programs"] if p["id"] == program_id)


class RealFileTest(unittest.TestCase):
    def test_real_file_passes(self):
        self.assertEqual(validate.validate_file(ROOT / "schedule.json"), [])

    def test_real_file_has_seven_programs(self):
        self.assertEqual(len(REAL["programs"]), 7)

    def test_real_file_is_small(self):
        self.assertLess((ROOT / "schedule.json").stat().st_size, validate.MAX_FILE_BYTES)


class RuleTest(unittest.TestCase):
    def assertFails(self, d, fragment):
        errors = validate.validate_document(d)
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")

    def test_schema_version(self):
        d = doc()
        d["schemaVersion"] = 2
        self.assertFails(d, "schemaVersion")

    def test_generated_at(self):
        d = doc()
        d["generatedAt"] = "2026-11-15"
        self.assertFails(d, "generatedAt")

    def test_unknown_root_key(self):
        d = doc()
        d["extra"] = 1
        self.assertFails(d, "unknown keys")

    def test_duplicate_program_id(self):
        d = doc()
        d["programs"].append(copy.deepcopy(d["programs"][0]))
        self.assertFails(d, "duplicate ids")

    def test_duplicate_item_id(self):
        d = doc()
        d["items"].append(copy.deepcopy(d["items"][0]))
        self.assertFails(d, "duplicate ids")

    def test_bad_ids(self):
        for bad in ("has space", "x" * 41, "", "한글"):
            d = doc()
            program(d, "hope1")["id"] = bad
            self.assertFails(d, "id must match")

    def test_unknown_status(self):
        d = doc()
        item(d, "hope1-2026-1")["status"] = "open"
        self.assertFails(d, "status must be one of")

    def test_bad_date_format(self):
        d = doc()
        item(d, "hope1-2026-1")["start"] = "2026/03/03"
        self.assertFails(d, "needs start and end")

    def test_impossible_date(self):
        d = doc()
        item(d, "hope1-2026-1")["end"] = "2026-02-30"
        self.assertFails(d, "needs start and end")

    def test_start_after_end(self):
        d = doc()
        item(d, "hope1-2026-1")["start"] = "2026-03-14"
        self.assertFails(d, "start is after end")

    def test_dated_status_needs_dates(self):
        for status in validate.DATED_STATUSES:
            d = doc()
            it = item(d, "hope1-2027-1")
            it["status"] = status
            it["expectedMonth"] = None
            self.assertFails(d, f"{status} needs start and end")

    def test_expected_needs_month_and_no_dates(self):
        d = doc()
        item(d, "hope1-2027-1")["expectedMonth"] = None
        self.assertFails(d, "expectedMonth as YYYY-MM")
        d = doc()
        item(d, "hope1-2027-1")["expectedMonth"] = "2027-13"
        self.assertFails(d, "expectedMonth as YYYY-MM")
        d = doc()
        item(d, "hope1-2027-1")["start"] = "2027-03-01"
        self.assertFails(d, "keep start and end null")

    def test_expected_month_only_for_expected(self):
        d = doc()
        item(d, "hope1-2026-1")["expectedMonth"] = "2026-03"
        self.assertFails(d, "expectedMonth only")

    def test_unknown_program_reference(self):
        d = doc()
        item(d, "hope1-2026-1")["programId"] = "nope"
        self.assertFails(d, "is not a program")

    def test_item_id_prefix(self):
        d = doc()
        item(d, "hope1-2026-1")["programId"] = "hope2"
        self.assertFails(d, "must start with")

    def test_missing_and_unknown_item_keys(self):
        d = doc()
        del item(d, "hope1-2026-1")["sourceUrl"]
        self.assertFails(d, "missing keys")
        d = doc()
        item(d, "hope1-2026-1")["region"] = "x"
        self.assertFails(d, "unknown keys")

    def test_end_time(self):
        d = doc()
        item(d, "cultureCard-2026-1")["endTime"] = "6pm"
        self.assertFails(d, "endTime must be HH:MM")
        d = doc()
        item(d, "hope1-2027-1")["endTime"] = "18:00"
        self.assertFails(d, "endTime needs a dated status")

    def test_reference_window(self):
        d = doc()
        item(d, "hope1-2027-1")["referenceWindow"] = {"start": "2026-03-13", "end": "2026-03-03"}
        self.assertFails(d, "referenceWindow")

    def test_http_url(self):
        d = doc()
        item(d, "hope1-2026-1")["sourceUrl"] = "http://hope.welfareinfo.or.kr/pds/GuideLine.pdf"
        self.assertFails(d, "must be https")

    def test_host_not_allowed(self):
        for url in (
            "https://www.yeonsu.go.kr/x",
            "https://hope.welfareinfo.or.kr.evil.example/x",
            "https://hope.welfareinfo.or.kr:8443/x",
            "https://user@www.korea.kr/x",
        ):
            d = doc()
            program(d, "hope1")["sources"][0]["url"] = url
            self.assertFails(d, "host not allowed")

    def test_banned_phrases(self):
        for phrase in validate.BANNED_PHRASES:
            d = doc()
            program(d, "hope1")["summary"]["who"] = f"누구나 {phrase}"
            self.assertFails(d, "banned phrase")
            d = doc()
            item(d, "hope1-2026-4")["note"] = phrase
            self.assertFails(d, "banned phrase")
            d = doc()
            program(d, "eitc")["eligibility"]["checkNote"] = phrase
            self.assertFails(d, "banned phrase")

    def test_text_limit(self):
        d = doc()
        program(d, "hope1")["summary"]["where"] = "가" * 81
        self.assertFails(d, "longer than")

    def test_summary_shape(self):
        d = doc()
        program(d, "hope1")["summary"]["bring"] = "신분증"
        self.assertFails(d, "bring must be a list")
        d = doc()
        del program(d, "hope1")["summary"]["caution"]
        self.assertFails(d, "summary keys")

    def test_channels(self):
        d = doc()
        program(d, "hope1")["channels"] = ["fax"]
        self.assertFails(d, "unknown value")
        d = doc()
        program(d, "hope1")["channels"] = []
        self.assertFails(d, "channels must not be empty")

    def test_sources(self):
        d = doc()
        program(d, "hope1")["sources"] = []
        self.assertFails(d, "sources must be a non-empty list")

    def test_eligibility_codes(self):
        d = doc()
        program(d, "hope1")["eligibility"]["anyBenefit"] = ["pension"]
        self.assertFails(d, "unknown value")
        d = doc()
        program(d, "hope1")["eligibility"]["anyMember"] = ["senior"]
        self.assertFails(d, "unknown value")
        d = doc()
        program(d, "hope1")["eligibility"]["needsEarner"] = "yes"
        self.assertFails(d, "needsEarner must be")
        d = doc()
        program(d, "hope1")["eligibility"]["maxResult"] = "unlikely"
        self.assertFails(d, "maxResult must be")
        d = doc()
        program(d, "hope1")["eligibility"]["alwaysShowNote"] = "yes"
        self.assertFails(d, "alwaysShowNote must be")
        d = doc()
        rule = program(d, "hope1")["eligibility"]
        rule["alwaysShowNote"] = True
        del rule["checkNote"]
        self.assertFails(d, "alwaysShowNote needs a checkNote")

    def test_soft_miss_needs_its_condition(self):
        d = doc()
        program(d, "cultureCard")["eligibility"]["softMiss"] = ["member"]
        self.assertFails(d, "softMiss 'member'")
        d = doc()
        program(d, "cultureCard")["eligibility"]["softMiss"] = ["earner"]
        self.assertFails(d, "softMiss 'earner'")
        d = doc()
        program(d, "eitc")["eligibility"]["softMiss"] = ["benefit"]
        self.assertFails(d, "softMiss 'benefit'")

    def test_last_checked(self):
        d = doc()
        item(d, "hope1-2026-1")["lastChecked"] = "2026-11"
        self.assertFails(d, "lastChecked")


class FileAndCliTest(unittest.TestCase):
    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = validate.main(["validate.py", *args])
        return code, out.getvalue()

    def test_real_file_exit_zero(self):
        code, out = self.run_main(str(ROOT / "schedule.json"))
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_bad_file_exit_one(self):
        d = doc()
        item(d, "hope1-2026-1")["status"] = "open"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            code, out = self.run_main(str(path))
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_usage_exit_two(self):
        self.assertEqual(self.run_main()[0], 2)
        self.assertEqual(self.run_main("/no/such/file.json")[0], 2)

    def test_too_big(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.json"
            path.write_bytes(b" " * (validate.MAX_FILE_BYTES + 1))
            self.assertIn("byte limit", validate.validate_file(path)[0])

    def test_not_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIn("not valid", validate.validate_file(path)[0])

    def test_root_not_object(self):
        self.assertTrue(validate.validate_document([]))


if __name__ == "__main__":
    unittest.main()
