"""Weekly stale-data check for schedule.json (research.md §5 14-day rule, Q3 A).

A round needs a human re-check when it is open now or opens within
WINDOW_DAYS days, and its lastChecked is more than STALE_DAYS days old. The
app stops sending "열렸어요" alerts at 14 days; this check fires at 10 so a
person has time to look first.

Which rounds count (Seoul dates):
  - confirmed / partialSuspended: start <= today + 30 and end >= today
  - expected: the first day of expectedMonth <= today + 30 and the month has
    not ended yet (so Jan–Mar rounds that are still "expected" are flagged)
  - suspended / closed: never

Usage:
  python3 -I tools/stale_check.py schedule.json [--today YYYY-MM-DD] [--message-file PATH]
Prints the result. Writes the Telegram text (UTF-8, at most MAX_MESSAGE_CHARS
characters) to --message-file only when at least one round is stale; the
workflow sends the file as is, and nothing when the file is absent.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as _dt
import json
import sys
from pathlib import Path

STALE_DAYS = 10
WINDOW_DAYS = 30
SEOUL = _dt.timezone(_dt.timedelta(hours=9))
OPEN_STATUSES = ("confirmed", "partialSuspended")
# Telegram sendMessage takes up to 4096 characters; keep well under it.
MAX_MESSAGE_CHARS = 3000


def seoul_today(now: _dt.datetime | None = None) -> _dt.date:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return now.astimezone(SEOUL).date()


def _month_bounds(value: str) -> tuple[_dt.date, _dt.date]:
    year, month = (int(part) for part in value.split("-"))
    last = calendar.monthrange(year, month)[1]
    return _dt.date(year, month, 1), _dt.date(year, month, last)


def in_window(item: dict, today: _dt.date) -> bool:
    horizon = today + _dt.timedelta(days=WINDOW_DAYS)
    status = item.get("status")
    if status in OPEN_STATUSES:
        start = _dt.date.fromisoformat(item["start"])
        end = _dt.date.fromisoformat(item["end"])
        return start <= horizon and end >= today
    if status == "expected":
        first, last = _month_bounds(item["expectedMonth"])
        return first <= horizon and last >= today
    return False


def stale_items(doc: dict, today: _dt.date) -> list[dict]:
    result = []
    for item in doc.get("items", []):
        if not in_window(item, today):
            continue
        checked = _dt.date.fromisoformat(item["lastChecked"])
        if (today - checked).days > STALE_DAYS:
            result.append(item)
    return result


def build_message(items: list[dict], today: _dt.date) -> str:
    """The Telegram text: header, one line per round, footer.

    At most MAX_MESSAGE_CHARS characters (Telegram allows 4096). When the
    lines do not all fit, the first ones that do are kept whole and a
    "…외 N건" line counts the rest; the header always shows the full count.
    Counting characters here (not bytes in the shell) never cuts a Korean
    character in half, which Telegram would refuse.
    """
    header = f"[신청달력] 확인 필요 {len(items)}건 ({today.isoformat()} 기준)"
    footer = "공식 안내·지자체 공지를 확인하고 schedule.json의 lastChecked를 갱신하세요."
    lines = [f"- {item['id']} · {item['status']} · 마지막 확인 {item['lastChecked']}" for item in items]
    used = [0]
    for line in lines:
        used.append(used[-1] + len(line) + 1)
    fixed = len(header) + 1 + len(footer)
    for shown in range(len(lines), -1, -1):
        omitted = len(lines) - shown
        tail = f"…외 {omitted}건" if omitted else ""
        size = fixed + used[shown] + (len(tail) + 1 if tail else 0)
        if size <= MAX_MESSAGE_CHARS:
            break
    return "\n".join([header, *lines[:shown], *([tail] if tail else []), footer])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("schedule", type=Path)
    parser.add_argument("--today", type=_dt.date.fromisoformat, default=None)
    parser.add_argument("--message-file", type=Path, default=None)
    args = parser.parse_args(argv)

    doc = json.loads(args.schedule.read_text(encoding="utf-8"))
    today = args.today or seoul_today()
    items = stale_items(doc, today)
    if not items:
        print(f"stale_check: 0 rounds need a re-check ({today.isoformat()})")
        return 0
    message = build_message(items, today)
    print(message)
    if args.message_file is not None:
        args.message_file.write_text(message, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
