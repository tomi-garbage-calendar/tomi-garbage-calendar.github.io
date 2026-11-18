import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from pipeline import AREAS, load_approved


def ics_escape(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold(line):
    result = []
    chunk = ""
    size = 0
    for char in line:
        length = len(char.encode("utf-8"))
        if size + length > 75:
            result.append(chunk)
            chunk, size = " ", 1
        chunk += char
        size += length
    return "\r\n".join([*result, chunk])


def calendar_file(path, area, events, stamp):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Tomi Garbage Calendar//JA",
             "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{ics_escape(AREAS[area])} ごみ収集"]
    for day, item in sorted(events):
        when = date.fromisoformat(day)
        uid = sha256(f"{area}|{day}|{item}".encode("utf-8")).hexdigest()
        lines += ["BEGIN:VEVENT", f"UID:{uid}@tomi-garbage-calendar.github.io",
                  f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{when:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{when + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{ics_escape(item)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    path.write_bytes(("\r\n".join(map(fold, lines)) + "\r\n").encode("utf-8"))


def generate(years, out):
    if not years:
        raise SystemExit("確認済みJSONがないためICSを生成できません")
    schedules = defaultdict(list)
    for data in years.values():
        for event in data["events"]:
            schedules[event["district"]].append((event["date"], event["item"]))
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for area in AREAS:
        calendar_file(out / f"{area}.ics", area, schedules[area], stamp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="確認済みJSONから地区別ICSを生成")
    parser.add_argument("output", type=Path)
    generate(load_approved(), parser.parse_args().output)
