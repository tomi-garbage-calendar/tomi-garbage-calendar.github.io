import argparse
import json
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from shutil import copyfile
from xml.etree.ElementTree import Element, SubElement, tostring

from generate_ics import generate
from normalize_items import LOCATION_NAMES, publication_data
from pipeline import AREAS, OFFICIAL, load_approved, write

SITE = Path(__file__).resolve().parents[1] / "site"
SITE_URL = "https://tomi-garbage-calendar.github.io/"
SITE_NAME = "東御市ごみ出しカレンダー（非公式）"


def page_metadata(path, title, description, page_type, **properties):
    url = SITE_URL + path
    fields = {"title": title, "description": description, "type": "website",
              "url": url, "site_name": SITE_NAME, "locale": "ja_JP", "image": SITE_URL + "og-calendar.png",
              "image:width": "1200", "image:height": "630", "image:alt": SITE_NAME}
    schema = {"@context": "https://schema.org", "@type": page_type, "url": url, "name": title,
              "description": description, "inLanguage": "ja", **properties}
    structured = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")
    return "\n".join([
        f'<title>{escape(title)}</title>',
        f'<meta name="description" content="{escape(description)}">',
        f'<link rel="canonical" href="{escape(url)}">',
        *(f'<meta property="og:{key}" content="{escape(value)}">' for key, value in fields.items()),
        f'<script type="application/ld+json">{structured}</script>',
    ])


def district_list(areas):
    return "<ul>" + "".join(f'<li><a href="{area}.html">{escape(AREAS[area])}の収集日</a></li>'
                              for area in areas) + "</ul>"


def annual_page(metadata, content):
    template = (SITE / "index.html").read_text(encoding="utf-8")
    footer = template.split("<footer>", 1)[1].split("</footer>", 1)[0]
    return ('<!doctype html><html lang="ja" prefix="og: https://ogp.me/ns#"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="theme-color" content="#fff" media="(prefers-color-scheme: light)">'
            '<meta name="theme-color" content="#000" media="(prefers-color-scheme: dark)">'
            f'{metadata}<link rel="stylesheet" href="calendar.css">'
            '<link rel="stylesheet" href="collection-location.css">'
            '<script type="module" src="collection-location.js"></script>'
            f'</head><body><main class="annual">{content}</main><footer>{footer}</footer></body></html>')


def home_page(areas):
    title = SITE_NAME
    description = "長野県東御市の非公式ごみカレンダー。地区を選んで今日・明日・明後日や年間のごみ収集日、品目、出す場所を確認できます。"
    metadata = page_metadata("", title, description, "WebSite", alternateName="東御市ごみカレンダー")
    links = ('<details class="district-directory"><summary>地区別の年間収集予定</summary>'
             f'{district_list(areas)}</details>')
    template = (SITE / "index.html").read_text(encoding="utf-8")
    return template.replace("<!-- page-metadata -->", metadata).replace("<!-- static-links -->", links)


def write_crawl_files(out, paths):
    sitemap = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for path in paths:
        SubElement(SubElement(sitemap, "url"), "loc").text = SITE_URL + path
    (out / "sitemap.xml").write_bytes(tostring(sitemap, encoding="utf-8", xml_declaration=True))
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n"
        "\n# AI向けのサイト案内と収集予定\n"
        f"# {SITE_URL}llms.txt\n# {SITE_URL}llms-full.txt\n", encoding="utf-8")


def write_llms_files(out, years):
    intro = [
        f"# {SITE_NAME}",
        "",
        "> 長野県東御市の地区別ごみ収集予定を提供する非公式サイトです。",
        "",
        "確認済みの市民カレンダーをもとにしています。対象年度、地区、日付を確認してください。",
        "収集品目や場所の詳細は東御市の公式資料と地区の案内を確認してください。",
        "",
    ]
    links = ["## 地区別の年間収集予定", ""]
    for area, name in AREAS.items():
        links.append(f"- [{name}]({SITE_URL}{area}.html)")
    links.extend([
        "",
        "## データと出典",
        "",
        f"- [全地区の収集予定（テキスト）]({SITE_URL}llms-full.txt)",
        f"- [公開年度と地区一覧（JSON）]({SITE_URL}data/index.json)",
        f"- [東御市公式のごみ出しカレンダー]({OFFICIAL})",
    ])
    for year in sorted(years, reverse=True):
        links.append(f"- [{year}年度の収集予定（JSON）]({SITE_URL}data/{year}.json)")
    (out / "llms.txt").write_text("\n".join([*intro, *links]) + "\n", encoding="utf-8")

    full = [*intro, "収集場所は品目ごとに表示しています。クリーンセンター休日受入は施設の受入予定です。", ""]
    for year, data in sorted(years.items(), reverse=True):
        full.extend([f"## {year}年度", "", f"- [公開データ]({SITE_URL}data/{year}.json)"])
        for source in data["sources"].values():
            full.append(f"- [市民カレンダーの出典PDF]({source['url']})")
        for area, name in AREAS.items():
            full.extend(["", f"### {name}", "", f"[地区別の年間予定]({SITE_URL}{area}.html)", ""])
            days = defaultdict(list)
            for event in data["events"]:
                if event["district"] != area:
                    continue
                label = event["item"]
                if event["collection_type"] != "clean-center":
                    label += f"（{LOCATION_NAMES[event['location_type']]}）"
                if label not in days[event["date"]]:
                    days[event["date"]].append(label)
            for day, items in sorted(days.items()):
                full.append(f"- {day} {'、'.join(items)}")
    (out / "llms-full.txt").write_text("\n".join(full) + "\n", encoding="utf-8")


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
             '<a href="./"><前のページに戻る</a></nav>'
             f'<h1>{escape(title)}のごみ収集日</h1></header>',
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
    description = (f"東御市の{title}の{max(years)}年度のごみ収集日を、月別の日付・品目・出す場所で確認できます。"
                   "年間予定のICS購読にも対応した非公式カレンダーです。")
    metadata = page_metadata(f"{area}.html", f"{title}のごみ収集日 | {SITE_NAME}", description, "CollectionPage",
                             isPartOf={"@type": "WebSite", "url": SITE_URL, "name": SITE_NAME})
    return annual_page(metadata, "".join(parts))


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
        for year, data in years.items():
            write(out / "data" / str(year) / f"{area}.json",
                  {"events": [event for event in data["events"] if event["district"] == area]})
        schedule = {year: [(e["date"], e["item"], e["item_id"], e["location_type"]) for e in data["events"]
                           if e["district"] == area]
                    for year, data in years.items()}
        (out / f"{area}.html").write_text(
            district_page(area, sorted(years, reverse=True), schedule, item_icons), encoding="utf-8")
    write(out / "data" / "index.json", {"districts": AREAS, "years": sorted(years), "districtFiles": True,
                                      "itemIcons": item_icons, "locationNames": LOCATION_NAMES})
    (out / "index.html").write_text(home_page(AREAS), encoding="utf-8")
    write_crawl_files(out, ["", *(f"{area}.html" for area in AREAS)])
    write_llms_files(out, years)
    for filename in ("calendar.css", "calendar.js", "collection-icons.svg",
                     "google2ffc0f67c84a72b7.html",
                     "collection-location.css", "collection-location.js", "og-calendar.png"):
        copyfile(SITE / filename, out / filename)
    (out / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
