import argparse
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from shutil import copyfile

from generate_ics import generate
from pipeline import AREAS, OFFICIAL, load_approved, write

SITE = Path(__file__).resolve().parents[1] / "site"


STYLES = """
:root{font-family:system-ui,sans-serif;color:#203930;background:#f5f7f2;line-height:1.6}
body{max-width:64rem;margin:auto;padding:2rem 1rem}
h1{line-height:1.2;letter-spacing:.02em}a{color:#13644d;text-underline-offset:.18em}
nav ul,.districts{display:flex;flex-wrap:wrap;gap:.65rem;padding:0;list-style:none}
.download{display:inline-block;padding:.65rem 1rem;background:#e3efe4;border-radius:.55rem}
table{width:100%;border-collapse:collapse;background:white}
th,td{padding:.55rem .65rem;text-align:left;border-bottom:1px solid #dfe8df;vertical-align:top}
th[scope=row]{white-space:nowrap;width:6rem}
footer{margin-top:3rem;border-top:1px solid #cddacd;padding-top:1rem}
"""


def page(title, content):
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)} | 東御市ごみ収集カレンダー</title><style>{STYLES}</style></head>'
            f'<body><main>{content}</main><footer>非公式のカレンダーです。'
            f'<a href="{OFFICIAL}">東御市公式のごみ出しカレンダー</a></footer></body></html>')


def district_page(area, years, schedule):
    title = AREAS[area]
    navigation = "".join(f'<li><a href="#fy-{year}">{year}年度</a></li>' for year in years)
    parts = ['<p><a href="index.html">今日・明日・明後日</a></p>', f"<h1>{escape(title)}</h1>",
             f'<p><a class="download" href="{area}.ics">全年度のカレンダー（ICS）</a></p>',
             f'<nav aria-label="年度"><ul>{navigation}</ul></nav>']
    for year in years:
        parts.append(f'<section id="fy-{year}"><h2>{year}年度</h2>'
                     f'<p><a href="data/{year}.json">確認済みJSON</a></p>')
        grouped = defaultdict(lambda: defaultdict(list))
        for day, item in sorted(schedule[year]):
            grouped[day[:7]][day].append(item)
        for month, days in sorted(grouped.items()):
            month_date = date.fromisoformat(month + "-01")
            heading = f"{month_date.year}年{month_date.month}月"
            parts.append(f'<h3 id="month-{month}">{heading}</h3>'
                         f'<table aria-labelledby="month-{month}"><thead><tr>'
                         f'<th scope="col">日付</th><th scope="col">収集品目・受入</th>'
                         f'</tr></thead><tbody>')
            for day, items in sorted(days.items()):
                when = date.fromisoformat(day)
                label = f"{when.day}日（{'月火水木金土日'[when.weekday()]}）"
                parts.append(f'<tr><th scope="row"><time datetime="{day}">{label}</time></th>'
                             f'<td>{escape("、".join(items))}</td></tr>')
            parts.append("</tbody></table>")
        parts.append("</section>")
    return page(title, "".join(parts))


def build(out):
    years = load_approved()
    if not years:
        raise SystemExit("確認済みJSONがないため公開用ファイルを生成できません")
    if out.exists() and any(out.iterdir()):
        raise SystemExit("空の出力先を指定してください")
    out.mkdir(parents=True, exist_ok=True)
    for year, data in years.items():
        write(out / "data" / f"{year}.json", data)
    generate(years, out)
    for area in AREAS:
        schedule = {year: [(e["date"], e["item"]) for e in data["events"] if e["district"] == area]
                    for year, data in years.items()}
        (out / f"{area}.html").write_text(
            district_page(area, sorted(years, reverse=True), schedule), encoding="utf-8")
    write(out / "data" / "index.json", {"districts": AREAS, "years": sorted(years)})
    for filename in ("index.html", "calendar.css", "calendar.js"):
        copyfile(SITE / filename, out / filename)
    (out / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
