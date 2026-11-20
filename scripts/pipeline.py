import argparse
from collections import Counter
from datetime import date
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from extract import DISTRICTS, ITEMS, extract_pdf, normalize
from normalize_items import normalize_extraction


OFFICIAL = "https://www.city.tomi.nagano.jp/category/gomi/150910.html"
ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / "data" / "approved"
TITLES = {
    "田中地区（常田区・田中区を除く）、滋野地区": "tanaka-shigeno",
    "常田区・田中区、祢津地区、和地区": "tanaka-ne-tsu-kanou",
    "北御牧地区": "kitamimaki",
}
AREAS = {key: name for edition in DISTRICTS.values() for key, name in edition.items()}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def official_url(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.netloc == "www.city.tomi.nagano.jp"


def fetch(url, limit):
    if not official_url(url):
        raise ValueError(f"公式サイト外のURL: {url}")
    with urlopen(url, timeout=45) as response:
        if not official_url(response.geturl()):
            raise ValueError(f"公式サイト外への転送: {url}")
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError(f"ダウンロードのサイズ上限を超過: {url}")
    return body


class CalendarLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.years = {}
        self.year = None
        self.heading = None

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.heading = []
        if tag == "a" and self.year is not None:
            attrs = dict(attrs)
            href = attrs.get("href", "")
            if not urlsplit(href).path.lower().endswith(".pdf"):
                return
            edition = next((key for title, key in TITLES.items()
                            if normalize(title) == normalize(attrs.get("title", ""))), None)
            links = self.years[self.year]
            if edition is None or edition in links:
                raise ValueError(f"{self.year}年度: 未対応または重複した公式PDFリンク {href}")
            links[edition] = urljoin(OFFICIAL, href)

    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if tag == "h2" and self.heading is not None:
            match = re.fullmatch(r"(?:令和([0-9]+)|([0-9]{4}))年度市民カレンダー",
                                 normalize("".join(self.heading)))
            self.year = (2018 + int(match[1]) if match[1] else int(match[2])) if match else None
            if self.year is not None:
                self.years.setdefault(self.year, {})
            self.heading = None


def discover():
    parser = CalendarLinks()
    parser.feed(fetch(OFFICIAL, 2_000_000).decode("utf-8"))
    if not parser.years or any(links.keys() != DISTRICTS.keys() for links in parser.years.values()):
        raise ValueError("公式ページから年度ごとの3種類のPDFを確認できません")
    return parser.years


def validate(data, year):
    if data["schema_version"] != 1 or data["fiscal_year"] != year or data["districts"] != AREAS:
        raise ValueError(f"{year}: JSON形式、年度または地区が不正です")
    sources = data["sources"]
    if sources.keys() != DISTRICTS.keys() or len({s["url"] for s in sources.values()}) != 3:
        raise ValueError(f"{year}: PDFの版が不足または重複しています")
    for source in sources.values():
        if not official_url(source["url"]) or not re.fullmatch("[a-f0-9]{64}", source["sha256"]):
            raise ValueError(f"{year}: PDFの出典が不正です")
    start, end = date(year, 4, 1), date(year + 1, 4, 1)
    events = set()
    coverage = Counter()
    for event in data["events"]:
        area, day, item = (event[key] for key in ("district", "date", "item"))
        when = date.fromisoformat(day)
        key = (area, day, item)
        if (area not in AREAS or item not in ITEMS or when.isoformat() != day
                or not start <= when < end or key in events):
            raise ValueError(f"{year}: 収集予定が不正です {event}")
        events.add(key)
        if item == "もやせるごみ":
            coverage[area, when.month] += 1
    for area in AREAS:
        for month in range(1, 13):
            if not 4 <= coverage[area, month] <= 13:
                raise ValueError(f"{year}: {area} {month}月のもやせるごみの件数が異常です")


def load_approved():
    result = {}
    for path in sorted(APPROVED.glob("*.json")):
        year = int(path.stem)
        data = read(path)
        validate(data, year)
        result[year] = data
    return result


def download_sources(links, cache):
    sources = {}
    for edition, url in links.items():
        pdf = fetch(url, 50_000_000)
        if not pdf.startswith(b"%PDF-"):
            raise ValueError(f"PDF形式ではありません: {url}")
        sha = digest(pdf)
        path = cache / "pdf" / f"{sha}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf)
        sources[edition] = {"url": url, "sha256": sha}
    return sources


def same_pdfs(sources, approved):
    return all(source["sha256"] == approved["sources"][edition]["sha256"]
               for edition, source in sources.items())


def verify_publication():
    approved = load_approved()
    for year, links in sorted(discover().items()):
        if year not in approved or not same_pdfs(download_sources(links, ROOT / ".work"), approved[year]):
            raise ValueError(f"{year}年度の公式PDFに未確認の変更があるため公開を中止します")


def write_review_html(path, report):
    year = report["fiscal_year"]
    parts = [
        '<!doctype html><html lang="ja"><meta charset="utf-8">',
        f"<title>{year}年度 確認用レポート</title>",
        f"<h1>{year}年度 東御市ごみ収集カレンダー 確認用レポート</h1>",
        "<h2>公式PDF</h2><ul>",
    ]
    for title, edition in TITLES.items():
        source = report["sources"][edition]["source"]
        parts.append(f'<li><a href="{escape(source["url"])}">{escape(title)}</a> '
                     f'<code>{source["sha256"]}</code></li>')
    parts.append("</ul>")
    if report["issues"]:
        parts.append("<h2>要調査</h2><ul>")
        parts.extend(f"<li>{escape(issue)}</li>" for issue in report["issues"])
        parts.append("</ul>")
    for label, key in (("追加", "added"), ("削除", "removed")):
        rows = sorted(report[key], key=lambda item: (item[1], item[0], item[2]))
        parts.append(f"<h2>{label} {len(rows)}件</h2>")
        if rows:
            parts.append("<table><thead><tr><th>日付</th><th>地区</th><th>品目</th></tr></thead><tbody>")
            parts.extend(f"<tr><td>{day}</td><td>{escape(AREAS[area])}</td><td>{escape(item)}</td></tr>"
                         for area, day, item in rows)
            parts.append("</tbody></table>")
    parts.append("</html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def analyze(year, sources, old, cache, report):
    revision = digest(Path(__file__).with_name("extract.py").read_bytes())
    audit = {}
    all_events = set()
    issues = []
    for edition, source in sorted(sources.items()):
        sha = source["sha256"]
        if old and old["sources"][edition]["sha256"] == sha:
            all_events.update((e["district"], e["date"], e["item"]) for e in old["events"]
                              if e["district"] in DISTRICTS[edition])
            audit[edition] = {"source": source, "pages": [], "reused_approved": True}
            continue
        filename = f"{year}-{edition}-extraction.json"
        path = cache / "results" / f"{revision}-{year}-{edition}-{sha}.json"
        if path.exists():
            extraction = {**read(path), "source": source}
        else:
            try:
                pages = extract_pdf(cache / "pdf" / f"{sha}.pdf", year)
            except (ValueError, RuntimeError) as exc:
                issues.append(f"{edition}: {exc}")
                audit[edition] = {"source": source, "pages": []}
                continue
            extraction = {"fiscal_year": year, "edition": edition, "source": source, "pages": pages}
            write(path, extraction)
        write(report / filename, extraction)
        result = normalize_extraction(extraction)
        all_events.update(tuple(event) for event in result["events"])
        audit[edition] = {"source": source, "pages": extraction["pages"]}
        issues.extend(f"{edition}: {issue}" for issue in result["issues"])
    data = {"schema_version": 1, "fiscal_year": year, "districts": AREAS, "sources": sources,
            "events": [{"district": area, "date": day, "item": item}
                       for area, day, item in sorted(all_events)]}
    try:
        validate(data, year)
    except ValueError as exc:
        issues.append(str(exc))
    previous = {(e["district"], e["date"], e["item"]) for e in (old or {}).get("events", [])}
    review = {
        "fiscal_year": year, "issues": issues, "sources": audit,
        "added": sorted(all_events - previous), "removed": sorted(previous - all_events),
    }
    write(report / f"{year}-report.json", review)
    write_review_html(report / f"{year}-report.html", review)
    if not issues:
        path = report / f"{year}-candidate.json"
        write(path, data)
        return f"確認待ち {len(all_events)}件 / 候補ファイル SHA-256 `{digest(path.read_bytes())}`", True
    return f"要調査 {len(issues)}件 / {issues[0].splitlines()[0]}", False


def check(cache, report):
    approved = load_approved()
    report.mkdir(parents=True, exist_ok=True)
    for pattern in ("*-candidate.json", "*-report.json", "*-report.html", "*-extraction.json"):
        for stale in report.glob(pattern):
            stale.unlink()
    summary = ["# 東御市公式PDF 更新確認", ""]
    failed = False
    try:
        for year, links in sorted(discover().items()):
            sources = download_sources(links, cache)
            old = approved.get(year)
            if old and same_pdfs(sources, old):
                status = "確認済みPDFと同じ SHA-256"
            else:
                status, valid = analyze(year, sources, old, cache, report)
                failed |= not valid
            summary.append(f"- {year}年度 {status}")
    except Exception as exc:
        summary.append(f"- 取得または解析に失敗 {exc}")
        raise
    finally:
        (report / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    if failed:
        raise SystemExit("解析または検証で要調査の項目があります")


def approve(candidate, expected):
    if digest(candidate.read_bytes()) != expected:
        raise ValueError("確認した候補ファイルの SHA-256 と一致しません")
    data = read(candidate)
    year = int(data["fiscal_year"])
    validate(data, year)
    links = discover().get(year)
    if links is None or download_sources(links, ROOT / ".work") != data["sources"]:
        raise ValueError("候補の出典が現在掲載中の公式PDFと一致しません")
    write(APPROVED / f"{year}.json", data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    checker = commands.add_parser("check")
    checker.add_argument("--cache", type=Path, default=ROOT / ".work")
    checker.add_argument("--report", type=Path, default=ROOT / ".work" / "review")
    approver = commands.add_parser("approve")
    approver.add_argument("candidate", type=Path)
    approver.add_argument("sha256")
    normalizer = commands.add_parser("normalize")
    normalizer.add_argument("extraction", type=Path)
    normalizer.add_argument("output", type=Path)
    commands.add_parser("verify-publication")
    args = parser.parse_args()
    if args.command == "check":
        check(args.cache, args.report)
    elif args.command == "approve":
        approve(args.candidate, args.sha256)
    elif args.command == "normalize":
        write(args.output, normalize_extraction(read(args.extraction)))
    else:
        verify_publication()
