import argparse
import json
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from shutil import copyfile

from generate_ics import generate
from normalize_items import LOCATION_NAMES, publication_data
from pipeline import AREAS, OFFICIAL, load_approved, write

SITE = Path(__file__).resolve().parents[1] / "site"


def page(title, content):
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="theme-color" content="#fff" media="(prefers-color-scheme: light)">'
            '<meta name="theme-color" content="#000" media="(prefers-color-scheme: dark)">'
            f'<title>{escape(title)} | 東御市ごみ収集カレンダー</title>'
            '<link rel="stylesheet" href="calendar.css">'
            '<link rel="stylesheet" href="collection-location.css">'
            '<script type="module" src="collection-location.js"></script></head>'
            f'<body><main class="annual">{content}</main><footer><p>非公式のカレンダーです。</p>'
            f'<a href="{OFFICIAL}">東御市公式のごみ出しカレンダー</a></footer></body></html>')


def collection_item(item, item_id, location_type, item_icons):
    icon_id = item_icons.get(item_id)
    icon = ""
    if icon_id:
        icon = (f'<svg class="collection-icon" aria-hidden="true">'
                f'<use href="collection-icons.svg#{escape(icon_id)}"></use></svg>')
    return (f'<span class="collection-item">{icon}<span><span>{escape(item)}</span>'
            f'<button type="button" class="collection-location" aria-haspopup="dialog" '
            f'data-location="{escape(location_type)}" data-item="{escape(item)}">'
            f'{LOCATION_NAMES[location_type]}</button></span></span>')


def district_page(area, years, schedule, item_icons):
    title = AREAS[area]
    navigation = "".join(f'<li><a href="#fy-{year}">{year}年度</a></li>' for year in years)
    parts = ['<header><nav aria-label="カレンダー">'
             '<a href="index.html">今日・明日・明後日</a></nav>'
             f'<h1>{escape(title)}</h1></header>',
             f'<nav class="annual-links" aria-label="年間予定">'
             f'<a href="{area}.ics">全年度のカレンダー（ICS）</a><ul>{navigation}</ul></nav>']
    for year in years:
        parts.append(f'<section id="fy-{year}"><h2>{year}年度</h2>'
                     f'<p><a href="data/{year}.json">公開用JSON</a></p>')
        grouped = defaultdict(lambda: defaultdict(list))
        for day, item, item_id, location_type in sorted(schedule[year]):
            grouped[day[:7]][day].append((item, item_id, location_type))
        months = [date(year + (month < 4), month, 1) for month in (*range(4, 13), 1, 2, 3)]
        month_links = "".join(f'<li><a href="#month-{month:%Y-%m}" '
                              f'aria-label="{month.year}年{month.month}月">{month.month}</a></li>'
                              for month in months)
        parts.append(f'<div class="annual-calendar"><nav class="month-index" aria-label="{year}年度の月">'
                     f'<ol>{month_links}</ol></nav><div class="annual-months">')
        for month_date in months:
            month = month_date.strftime("%Y-%m")
            heading = f"{month_date.year}年{month_date.month}月"
            parts.append(f'<section class="result annual-month" id="month-{month}" '
                         f'aria-labelledby="heading-{month}">'
                         f'<h3 id="heading-{month}">{heading}</h3>')
            days = grouped.get(month)
            if not days:
                parts.append('<p>収集予定はありません。</p></section>')
                continue
            parts.append(f'<table aria-labelledby="heading-{month}"><thead><tr>'
                         f'<th scope="col">日付</th><th scope="col">収集品目・受入</th>'
                         f'</tr></thead><tbody>')
            for day, items in sorted(days.items()):
                when = date.fromisoformat(day)
                label = f"{when.day}日（{'月火水木金土日'[when.weekday()]}）"
                item_labels = "".join(collection_item(item, item_id, location_type, item_icons)
                                      for item, item_id, location_type in items)
                parts.append(f'<tr><th scope="row"><time datetime="{day}">{label}</time></th>'
                             f'<td>{item_labels}</td></tr>')
            parts.append("</tbody></table></section>")
        parts.append("</div></div></section>")
    return page(title, "".join(parts))


def build(out):
    years = {year: publication_data(data) for year, data in load_approved().items()}
    if not years:
        raise SystemExit("確認済みJSONがないため公開用ファイルを生成できません")
    if out.exists() and any(out.iterdir()):
        raise SystemExit("空の出力先を指定してください")
    item_icons = json.loads((SITE / "collection-icons.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    for year, data in years.items():
        write(out / "data" / f"{year}.json", data)
    generate(years, out)
    for area in AREAS:
        schedule = {year: [(e["date"], e["item"], e["item_id"], e["location_type"]) for e in data["events"]
                           if e["district"] == area]
                    for year, data in years.items()}
        (out / f"{area}.html").write_text(
            district_page(area, sorted(years, reverse=True), schedule, item_icons), encoding="utf-8")
    write(out / "data" / "index.json", {"districts": AREAS, "years": sorted(years),
                                      "itemIcons": item_icons, "locationNames": LOCATION_NAMES})
    for filename in ("index.html", "calendar.css", "calendar.js", "collection-icons.svg",
                     "collection-location.css", "collection-location.js"):
        copyfile(SITE / filename, out / filename)
    (out / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
