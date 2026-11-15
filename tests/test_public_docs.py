"""The repo is public: its docs name no person, local path or SSH host alias."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PUBLIC_DOCS = [README, *sorted((ROOT / "ops" / "evidence").glob("*.md"))]

# git@github-<alias>: is a per-machine ~/.ssh/config alias, not a GitHub host.
SSH_ALIAS_RE = re.compile(r"git@github-[^\s:]*:")
# A home-directory path, but not "/home/" inside a cited URL's path.
LOCAL_PATH_RE = re.compile(r"(?<![\w.%/-])/(?:Users|home)/|~/")


class PublicDocsTest(unittest.TestCase):
    def test_docs_exist(self):
        self.assertGreaterEqual(len(PUBLIC_DOCS), 2)

    def test_patterns(self):
        self.assertIsNotNone(LOCAL_PATH_RE.search("see /Users/someone/x"))
        self.assertIsNotNone(LOCAL_PATH_RE.search("`/home/someone/x`"))
        self.assertIsNotNone(LOCAL_PATH_RE.search("in ~/Documents"))
        self.assertIsNone(LOCAL_PATH_RE.search("https://www.example.go.kr/home/main.do"))
        self.assertIsNotNone(SSH_ALIAS_RE.search("git@github-someone:owner/repo.git"))
        self.assertIsNone(SSH_ALIAS_RE.search("git@github.com:owner/repo.git"))

    def test_no_ssh_host_alias_or_local_path(self):
        for path in PUBLIC_DOCS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIsNone(SSH_ALIAS_RE.search(text))
                self.assertIsNone(LOCAL_PATH_RE.search(text))

    def test_readme_names_a_role_not_a_person(self):
        # Owner steps name the role. (A name list would itself publish the
        # names, so this pins the role wording at both places instead.)
        text = README.read_text(encoding="utf-8")
        self.assertIn("(push는 저장소 소유자)", text)
        self.assertIn("## 저장소 소유자가 할 일", text)
        self.assertIn("git@github.com:jinhom6225/benefit-calendar-data.git", text)

if __name__ == "__main__":
    unittest.main()
