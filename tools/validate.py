"""Validate schedule.json for the 놓치지마 신청달력 app (benefit_calendar).

Usage:  python3 -I tools/validate.py schedule.json
Exit 0 when the file passes, 1 when it has errors (each printed on its own
line), 2 on usage errors. Standard library only.

The rules mirror research.md §6-2 of the app (schema), §6-4 (link hosts) and
the banned-phrase list in §2. The app is more lenient (it drops bad records
one by one); this script is strict so a bad record never reaches Pages.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024
SCHEMA_VERSION = 1

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
GENERATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Link rule, decided on the raw text like the app's safeHttpsHost
# (lib/data/validation/url_rules.dart): urlsplit drops tab/CR/LF, ignores an
# empty userinfo or port and can raise, so it is not used. Python's "$" also
# matches before a final newline, hence \Z and the lookahead below.
MAX_URL_LENGTH = 2048
URL_AUTHORITY_RE = re.compile(r"https://([A-Za-z0-9.-]+)(?=[/?#]|\Z)")
HOST_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+\Z")
# A last label WHATWG parses as IPv4: all digits, or 0x plus hex digits.
IPV4_LAST_LABEL_RE = re.compile(r"(?:[0-9]+|0x[0-9a-f]*)\Z")
# Stricter than the app, anywhere in the link: C0 controls, space, DEL, "\\".
UNSAFE_URL_CHARS_RE = re.compile(r"[\x00-\x20\x7f\\]")

STATUSES = ("confirmed", "expected", "partialSuspended", "suspended", "closed")
DATED_STATUSES = ("confirmed", "partialSuspended", "suspended", "closed")
CHANNELS = ("visit", "online", "hometax", "site")
BENEFITS = ("livelihood", "medical", "housing", "education", "nearPoor", "anyRecipient")
MEMBERS = ("youth", "student", "vulnerable")
SOFT_MISS = ("benefit", "earner", "member")
MAX_RESULTS = ("likely", "check")

# research.md §6-4 plus the Phase 0 correction (교육비 원클릭 is
# oneclick.neis.go.kr; oneclick.moe.go.kr does not resolve).
ALLOWED_HOSTS = frozenset(
    {
        "hope.welfareinfo.or.kr",
        "www.mohw.go.kr",
        "www.bokjiro.go.kr",
        "www.hometax.go.kr",
        "www.nts.go.kr",
        "www.energyv.or.kr",
        "www.mnuri.kr",
        "www.korea.kr",
        "www.moe.go.kr",
        "oneclick.neis.go.kr",
    }
)

# research.md §2·§6-2: assertive or action phrases the data must never show.
BANNED_PHRASES = ("받을 수 있습니다", "가입하기", "계좌 개설", "공식 앱")

# Short texts for a big-font senior UI.
TEXT_LIMITS = {
    "name": 30,
    "who": 120,
    "amount": 120,
    "where": 80,
    "bring": 60,
    "caution": 160,
    "checkNote": 120,
    "label": 40,
    "note": 120,
    "sourceLabel": 40,
}

PROGRAM_KEYS = {"id", "name", "summary", "channels", "eligibility", "sources", "lastChecked"}
SUMMARY_KEYS = {"who", "amount", "where", "bring", "caution"}
ELIGIBILITY_KEYS = {
    "anyBenefit", "needsEarner", "anyMember", "softMiss", "maxResult", "alwaysShowNote", "checkNote",
}
ITEM_REQUIRED = {"id", "programId", "label", "status", "start", "end", "expectedMonth", "sourceUrl", "lastChecked"}
ITEM_OPTIONAL = {"endTime", "referenceWindow", "note"}


class Errors:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.items.append(f"{where}: {message}")


def parse_date(value: object) -> _dt.date | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        return None


def safe_https_host(url: str) -> str | None:
    """The lowercased host of a plain https link, or None.

    Mirrors the app's safeHttpsHost: at most MAX_URL_LENGTH characters, the
    text right after "https://" up to the first "/", "?", "#" or the end is
    a bare ASCII host name (so userinfo "@", any port ":", "%", "\\",
    control or non-ASCII characters, empty labels and a trailing dot fail),
    and its last label is not IPv4-like. The ASCII check runs before
    lowercasing (U+212A KELVIN SIGN lowercases to "k").
    """
    if len(url) > MAX_URL_LENGTH:
        return None
    match = URL_AUTHORITY_RE.match(url)
    if match is None:
        return None
    host = match.group(1).lower()
    if not HOST_RE.match(host):
        return None
    if IPV4_LAST_LABEL_RE.match(host.rsplit(".", 1)[-1]):
        return None
    return host


def url_problem(url: str) -> str | None:
    """Why the link may not be shown, or None when it is fine."""
    if not url.startswith("https://"):
        return f"url must be https: {url!r}"
    if not url.isascii() or UNSAFE_URL_CHARS_RE.search(url):
        return f"url has unsafe characters: {url!r}"
    host = safe_https_host(url)
    if host is None or host not in ALLOWED_HOSTS:
        return f"host not allowed: {url!r}"
    return None


def check_url(url: object, where: str, errors: Errors) -> None:
    if not isinstance(url, str) or not url:
        errors.add(where, "url must be a non-empty string")
        return
    problem = url_problem(url)
    if problem is not None:
        errors.add(where, problem)


def check_text(value: object, kind: str, where: str, errors: Errors, required: bool = True) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        errors.add(where, f"{kind} must be a non-empty string")
        return
    if len(value) > TEXT_LIMITS[kind]:
        errors.add(where, f"{kind} longer than {TEXT_LIMITS[kind]} chars ({len(value)})")
    for phrase in BANNED_PHRASES:
        if phrase in value:
            errors.add(where, f"banned phrase {phrase!r}")


def check_code_list(value: object, allowed: tuple[str, ...], where: str, errors: Errors) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errors.add(where, "must be a list of strings")
        return
    for v in value:
        if v not in allowed:
            errors.add(where, f"unknown value {v!r}")
    if len(set(value)) != len(value):
        errors.add(where, "duplicate values")


def check_last_checked(value: object, where: str, errors: Errors) -> None:
    if parse_date(value) is None:
        errors.add(where, "lastChecked must be YYYY-MM-DD")


def check_eligibility(rule: object, where: str, errors: Errors) -> None:
    if not isinstance(rule, dict):
        errors.add(where, "eligibility must be an object")
        return
    extra = set(rule) - ELIGIBILITY_KEYS
    if extra:
        errors.add(where, f"unknown keys {sorted(extra)}")
    for key in ("anyBenefit", "needsEarner", "anyMember"):
        if key not in rule:
            errors.add(where, f"missing {key}")
    check_code_list(rule.get("anyBenefit", []), BENEFITS, f"{where}.anyBenefit", errors)
    check_code_list(rule.get("anyMember", []), MEMBERS, f"{where}.anyMember", errors)
    check_code_list(rule.get("softMiss", []), SOFT_MISS, f"{where}.softMiss", errors)
    if not isinstance(rule.get("needsEarner"), bool):
        errors.add(where, "needsEarner must be true or false")
    if rule.get("maxResult", "likely") not in MAX_RESULTS:
        errors.add(where, f"maxResult must be one of {MAX_RESULTS}")
    soft = rule.get("softMiss", [])
    if isinstance(soft, list):
        # A soft miss on a condition the rule does not have would be dead data.
        if "benefit" in soft and not rule.get("anyBenefit"):
            errors.add(where, "softMiss 'benefit' without anyBenefit")
        if "member" in soft and not rule.get("anyMember"):
            errors.add(where, "softMiss 'member' without anyMember")
        if "earner" in soft and rule.get("needsEarner") is not True:
            errors.add(where, "softMiss 'earner' without needsEarner")
    if not isinstance(rule.get("alwaysShowNote", False), bool):
        errors.add(where, "alwaysShowNote must be true or false")
    if rule.get("alwaysShowNote") is True and not rule.get("checkNote"):
        errors.add(where, "alwaysShowNote needs a checkNote")
    check_text(rule.get("checkNote"), "checkNote", f"{where}.checkNote", errors, required=False)


def check_program(program: object, index: int, errors: Errors) -> str | None:
    where = f"programs[{index}]"
    if not isinstance(program, dict):
        errors.add(where, "must be an object")
        return None
    pid = program.get("id")
    if isinstance(pid, str):
        where = f"programs[{pid}]"
    if not isinstance(pid, str) or not ID_RE.match(pid):
        errors.add(where, "id must match [A-Za-z0-9_-]{1,40}")
    missing = PROGRAM_KEYS - set(program)
    extra = set(program) - PROGRAM_KEYS
    if missing:
        errors.add(where, f"missing keys {sorted(missing)}")
    if extra:
        errors.add(where, f"unknown keys {sorted(extra)}")
    check_text(program.get("name"), "name", f"{where}.name", errors)

    summary = program.get("summary")
    if not isinstance(summary, dict):
        errors.add(where, "summary must be an object")
    else:
        if set(summary) != SUMMARY_KEYS:
            errors.add(where, f"summary keys must be {sorted(SUMMARY_KEYS)}")
        for key in ("who", "amount", "where", "caution"):
            check_text(summary.get(key), key, f"{where}.summary.{key}", errors)
        bring = summary.get("bring")
        if not isinstance(bring, list):
            errors.add(where, "summary.bring must be a list (may be empty)")
        else:
            for n, entry in enumerate(bring):
                check_text(entry, "bring", f"{where}.summary.bring[{n}]", errors)

    channels = program.get("channels")
    check_code_list(channels, CHANNELS, f"{where}.channels", errors)
    if isinstance(channels, list) and not channels:
        errors.add(where, "channels must not be empty")
    check_eligibility(program.get("eligibility"), f"{where}.eligibility", errors)

    sources = program.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.add(where, "sources must be a non-empty list")
    else:
        for n, source in enumerate(sources):
            swhere = f"{where}.sources[{n}]"
            if not isinstance(source, dict) or set(source) != {"label", "url"}:
                errors.add(swhere, "must be {label, url}")
                continue
            check_text(source.get("label"), "sourceLabel", swhere, errors)
            check_url(source.get("url"), swhere, errors)
    check_last_checked(program.get("lastChecked"), where, errors)
    return pid if isinstance(pid, str) else None


def check_item(item: object, index: int, program_ids: set[str], errors: Errors) -> str | None:
    where = f"items[{index}]"
    if not isinstance(item, dict):
        errors.add(where, "must be an object")
        return None
    iid = item.get("id")
    if isinstance(iid, str):
        where = f"items[{iid}]"
    if not isinstance(iid, str) or not ID_RE.match(iid):
        errors.add(where, "id must match [A-Za-z0-9_-]{1,40}")
    missing = ITEM_REQUIRED - set(item)
    extra = set(item) - ITEM_REQUIRED - ITEM_OPTIONAL
    if missing:
        errors.add(where, f"missing keys {sorted(missing)}")
    if extra:
        errors.add(where, f"unknown keys {sorted(extra)}")
    if item.get("programId") not in program_ids:
        errors.add(where, f"programId {item.get('programId')!r} is not a program")
    elif isinstance(iid, str) and not iid.startswith(f"{item['programId']}-"):
        errors.add(where, "id must start with '<programId>-'")
    check_text(item.get("label"), "label", f"{where}.label", errors)
    check_text(item.get("note"), "note", f"{where}.note", errors, required=False)

    status = item.get("status")
    if status not in STATUSES:
        errors.add(where, f"status must be one of {STATUSES}")
    start, end = item.get("start"), item.get("end")
    if status in DATED_STATUSES:
        start_d, end_d = parse_date(start), parse_date(end)
        if start_d is None or end_d is None:
            errors.add(where, f"{status} needs start and end as YYYY-MM-DD")
        elif start_d > end_d:
            errors.add(where, "start is after end")
        if item.get("expectedMonth") is not None:
            errors.add(where, "expectedMonth only for status 'expected'")
    elif status == "expected":
        if start is not None or end is not None:
            errors.add(where, "expected rounds keep start and end null")
        month = item.get("expectedMonth")
        if not isinstance(month, str) or not MONTH_RE.match(month):
            errors.add(where, "expected needs expectedMonth as YYYY-MM")
    end_time = item.get("endTime")
    if end_time is not None:
        if not isinstance(end_time, str) or not TIME_RE.match(end_time):
            errors.add(where, "endTime must be HH:MM")
        if status not in DATED_STATUSES:
            errors.add(where, "endTime needs a dated status")
    ref = item.get("referenceWindow")
    if ref is not None:
        if not isinstance(ref, dict) or set(ref) != {"start", "end"}:
            errors.add(where, "referenceWindow must be {start, end}")
        else:
            rs, re_ = parse_date(ref["start"]), parse_date(ref["end"])
            if rs is None or re_ is None or rs > re_:
                errors.add(where, "referenceWindow needs valid start <= end")
    check_url(item.get("sourceUrl"), f"{where}.sourceUrl", errors)
    check_last_checked(item.get("lastChecked"), where, errors)
    return iid if isinstance(iid, str) else None


def validate_document(doc: object) -> list[str]:
    errors = Errors()
    if not isinstance(doc, dict):
        errors.add("root", "must be an object")
        return errors.items
    extra = set(doc) - {"schemaVersion", "generatedAt", "programs", "items"}
    if extra:
        errors.add("root", f"unknown keys {sorted(extra)}")
    if doc.get("schemaVersion") != SCHEMA_VERSION:
        errors.add("root", f"schemaVersion must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("generatedAt"), str) or not GENERATED_AT_RE.match(doc["generatedAt"]):
        errors.add("root", "generatedAt must be YYYY-MM-DDTHH:MM:SSZ")
    programs, items = doc.get("programs"), doc.get("items")
    if not isinstance(programs, list) or not programs:
        errors.add("root", "programs must be a non-empty list")
        programs = []
    if not isinstance(items, list):
        errors.add("root", "items must be a list")
        items = []

    program_ids: list[str] = []
    for n, program in enumerate(programs):
        pid = check_program(program, n, errors)
        if pid is not None:
            program_ids.append(pid)
    dupes = sorted({p for p in program_ids if program_ids.count(p) > 1})
    if dupes:
        errors.add("programs", f"duplicate ids {dupes}")

    item_ids: list[str] = []
    for n, item in enumerate(items):
        iid = check_item(item, n, set(program_ids), errors)
        if iid is not None:
            item_ids.append(iid)
    dupes = sorted({i for i in item_ids if item_ids.count(i) > 1})
    if dupes:
        errors.add("items", f"duplicate ids {dupes}")
    return errors.items


def validate_file(path: Path) -> list[str]:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        return [f"file: {len(raw)} bytes is over the {MAX_FILE_BYTES} byte limit"]
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"file: not valid UTF-8 JSON ({exc})"]
    return validate_document(doc)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 -I tools/validate.py schedule.json", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    problems = validate_file(path)
    for problem in problems:
        print(problem)
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
