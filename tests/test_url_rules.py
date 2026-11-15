"""tools/validate.py link rule: the same raw-text rule as the app's safeHttpsHost.

The app (lib/data/validation/url_rules.dart) decides on the raw text, not on a
parsed URL: plain https, a bare ASCII host name right after "://" (no
userinfo, port, "%", "\\", control or non-ASCII characters, no empty label or
trailing dot), not an IPv4 address, and the host exactly in the allowlist.
The validator is at least as strict, so it also rejects control characters,
spaces, backslashes and non-ASCII anywhere in the link.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import validate  # noqa: E402

REAL = json.loads((ROOT / "schedule.json").read_text(encoding="utf-8"))

BAD_URLS = (
    # Vectors from the security review (L3).
    "https://:@www.bokjiro.go.kr/",
    "https://www.bokjiro.go.kr:443/",
    "https://www.bokjiro.go.kr./",
    "https://www.bokjiro.go.kr.evil.com/",
    "https://evil.com\\@www.bokjiro.go.kr/",
    "https://www.bokjiro.go.kr%2F@evil.com/",
    "http://www.bokjiro.go.kr/",
    # Empty userinfo / empty port slip past urlsplit-based checks.
    "https://@www.bokjiro.go.kr/",
    "https://www.bokjiro.go.kr:/",
    # urlsplit drops tab, CR and LF before parsing.
    "https://www.bok\tjiro.go.kr/",
    "https://www.bok\njiro.go.kr/",
    # Python "$" matches before a final newline; the rule must not.
    "https://www.bokjiro.go.kr\n",
    # Control characters, space, DEL, backslash and non-ASCII after the host.
    "https://www.bokjiro.go.kr/\n",
    "https://www.bokjiro.go.kr/a\tb",
    "https://www.bokjiro.go.kr/a b",
    "https://www.bokjiro.go.kr/a\x00",
    "https://www.bokjiro.go.kr/a\x7f",
    "https://www.bokjiro.go.kr/a\\b",
    "https://www.bokjiro.go.kr/복지",
    "https://www.bоkjiro.go.kr/",  # Cyrillic o
    "https://www.bokjiro.go.Kr/",  # Kelvin sign lowercases to k
    # Other shapes.
    "https://www.bokjiro.go.kr@evil.com/",
    "https://[::1]/",
    "//www.bokjiro.go.kr/",
    "www.bokjiro.go.kr/",
    "https:/www.bokjiro.go.kr/",
    "https:///www.bokjiro.go.kr/",
    "javascript:alert(1)//www.bokjiro.go.kr/",
    " https://www.bokjiro.go.kr/",
    "https://www.bokjiro.go.kr/" + "a" * validate.MAX_URL_LENGTH,
)

GOOD_URLS = (
    "https://www.bokjiro.go.kr",
    "https://www.bokjiro.go.kr/",
    "https://www.bokjiro.go.kr?x=1",
    "https://www.bokjiro.go.kr#top",
    "https://oneclick.neis.go.kr/",
    "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=238977&mi=40397",
)


def real_urls() -> list[str]:
    urls = [s["url"] for p in REAL["programs"] for s in p["sources"]]
    urls += [i["sourceUrl"] for i in REAL["items"]]
    return urls


class SafeHttpsHostTest(unittest.TestCase):
    """The host reader alone, so IPv4 and label checks are not hidden by the allowlist."""

    def test_plain_hosts(self):
        self.assertEqual(validate.safe_https_host("https://example.com/x"), "example.com")
        self.assertEqual(validate.safe_https_host("https://a-b.example.com"), "a-b.example.com")
        self.assertEqual(validate.safe_https_host("https://WWW.Example.COM/"), "www.example.com")

    def test_rejected_hosts(self):
        for url in (
            "https://127.0.0.1/",
            "https://127.0.0.0x1/",
            "https://1.2.3.0x/",
            "https://example.0x1f/",
            "https://example.123/",
            "https://a..b/",
            "https://example.com./",
            "https://.example.com/",
            "https://example/",
            "https://-a.example.com/",
            "https://a-.example.com/",
            "https://example.com:443/",
            "https://u@example.com/",
            "https://example%2ecom/",
            "http://example.com/",
            "https://exaKmple.com/",
        ):
            with self.subTest(url=url):
                self.assertIsNone(validate.safe_https_host(url))

    def test_length_cap(self):
        base = "https://example.com/"
        self.assertEqual(validate.safe_https_host(base + "a" * (validate.MAX_URL_LENGTH - len(base))), "example.com")
        self.assertIsNone(validate.safe_https_host(base + "a" * (validate.MAX_URL_LENGTH - len(base) + 1)))

    def test_never_raises(self):
        for url in ("https://[", "https://[::1", "https://a]b/", "https://%zz/", ""):
            with self.subTest(url=url):
                self.assertIsNone(validate.safe_https_host(url))


class UrlProblemTest(unittest.TestCase):
    def test_bad_urls_rejected(self):
        for url in BAD_URLS:
            with self.subTest(url=url):
                self.assertIsNotNone(validate.url_problem(url))

    def test_good_urls_pass(self):
        for url in GOOD_URLS:
            with self.subTest(url=url):
                self.assertIsNone(validate.url_problem(url))

    def test_every_real_url_passes(self):
        urls = real_urls()
        self.assertGreater(len(urls), 10)
        for url in urls:
            with self.subTest(url=url):
                self.assertIsNone(validate.url_problem(url))

    def test_messages(self):
        self.assertIn("must be https", validate.url_problem("http://www.bokjiro.go.kr/"))
        self.assertIn("host not allowed", validate.url_problem("https://:@www.bokjiro.go.kr/"))
        self.assertIn("host not allowed", validate.url_problem("https://www.yeonsu.go.kr/"))
        self.assertIn("unsafe characters", validate.url_problem("https://www.bokjiro.go.kr/a b"))

    def test_bad_urls_fail_the_document(self):
        for url in BAD_URLS:
            with self.subTest(url=url):
                d = copy.deepcopy(REAL)
                d["programs"][0]["sources"][0]["url"] = url
                d["items"][0]["sourceUrl"] = url
                errors = validate.validate_document(d)
                self.assertTrue(any(".sources[0]" in e for e in errors), errors)
                self.assertTrue(any(".sourceUrl" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
