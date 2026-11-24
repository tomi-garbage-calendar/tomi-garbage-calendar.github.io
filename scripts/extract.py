import calendar
from collections import defaultdict
from datetime import date
import re
import unicodedata


DISTRICTS = {
    "tanaka-shigeno": {
        "tanaka": "田中地区（常田区・田中区を除く）", "shigeno": "滋野地区",
    },
    "tanaka-ne-tsu-kanou": {
        "tokida-tanaka": "常田区・田中区", "netsu": "祢津地区", "kanou": "和地区",
    },
    "kitamimaki": {
        "kitamimaki-east": "八重原・羽毛山・大日向地区",
        "kitamimaki-west": "下之城・御牧原・布下・島川原地区",
    },
}
RESOURCE_DISTRICTS = {
    "田中": ("tanaka", "tokida-tanaka"), "滋野": ("shigeno",),
    "祢津": ("netsu",), "和": ("kanou",),
}
ITEMS = set("""
もやせるごみ 生ごみ 容器包装プラ 汚れ容器包装プラ 容器包装以外プラ 茶色びん 無色びん
他色びん びん カン 金物・陶器等 トレー等 紙類 衣類 紙類・衣類 ペットボトル 有害ごみ
クリーンセンター休日受入 資源回収（新聞等） 資源回収（ペット等） 資源回収（びん）
""".split())

# Digests identify decoded PDF images, independently of the PDF's compression.
BURNABLE = {"2f5c59c5834f0a09471d8edfd5c118e8", "4cbf8277c395a8a72f6e5ff67f5f4cbe"}
NORTH_ICONS = {
    "624c3241feda13f6c5a1c6791439afa3": "kitamimaki-east",
    "57a97c271fd0be4cc970d7d30de7b721": "kitamimaki-west",
}
LABELED_ICONS = {
    "16fa49c96863dd683e41522fde64b067": "クリーンセンター休日受入",
    "331c1e96fe8663e015567338a9602a76": "金物・陶器等",
    "42a6c19d6717490eb3cc3eb725779879": "金物・陶器等",
}
KNOWN_FRAGMENTS = {"クリーンセン", "ター休日受入", "ト", "レー等", "蛍光管", "乾電池",
                   "ライター等", "東御の日"}


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def spans(page, textpage=None):
    import pymupdf

    return [span for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT,
                                          textpage=textpage)["blocks"]
            for line in block["lines"] for span in line["spans"]]


def extract_pdf(path, year):
    import pymupdf

    audit = []
    with pymupdf.open(path) as document:
        if len(document) != 6:
            raise ValueError("2か月×6ページの版面に対応しています")
        for index in range(len(document)):
            audit.append(extract_page(document.load_page(index), year, index))
    return audit


def extract_page(page, year, index):
    import pymupdf

    if abs(page.rect.width - 1031.81) > 1 or abs(page.rect.height - 1530.71) > 1:
        raise ValueError(f"{index + 1}ページの用紙サイズが未対応です")
    text = spans(page)
    if not text:
        ocr = ocr_cell(page, page.rect)
        raise ValueError(f"{index + 1}ページにテキスト層がありません。OCR結果: {ocr[:800]}")
    images = page.get_image_info(hashes=True)
    drawings = page.get_drawings()
    filled = [tuple(drawing["rect"]) for drawing in drawings if drawing["fill"] is not None]
    placed_images = [(pymupdf.Rect(i["bbox"]).tl + (pymupdf.Rect(i["bbox"]).br
                                                 - pymupdf.Rect(i["bbox"]).tl) / 2,
                      i["digest"].hex(), pymupdf.Rect(i["bbox"])) for i in images]
    cells = []
    for half, offset in enumerate((0, 710.5)):
        month = (index * 2 + (1 - half) + 3) % 12 + 1
        civil_year = year + (month < 4)
        heading = [s for s in text if 65 + offset < s["bbox"][1] < 165 + offset]
        headings = {normalize(s["text"]) for s in heading if s["size"] > 70}
        if headings != {str(month)} or f"({civil_year}年)" not in normalize(
            "".join(s["text"] for s in heading)
        ):
            raise ValueError(f"{index + 1}ページの年月見出しが想定と一致しません")
        anchors = defaultdict(list)
        days = calendar.monthrange(civil_year, month)[1]
        found = set()
        for s in text:
            x, y = s["bbox"][:2]
            number = normalize(s["text"])
            if not (42 < s["size"] < 52 and 187 < y - offset < 710
                    and re.fullmatch(r"[0-9]{1,2}", number)):
                continue
            day = int(number)
            if not 1 <= day <= days or day in found:
                raise ValueError(f"{civil_year}-{month:02}: 日付欄が重複または範囲外です")
            column = (date(civil_year, month, day).weekday() + 1) % 7
            week = ((date(civil_year, month, 1).weekday() + 1) % 7 + day - 1) // 7
            expected_y = (194, 307, 420, 533, 645, 700)[week]
            if abs(y - offset - expected_y) > 5 or abs(x - (59 if day < 10 else 43)
                                                       - column * 135.6) > 4:
                raise ValueError(f"{civil_year}-{month:02}-{day:02}: 日付欄の座標が未対応です")
            anchors[column].append((y, day))
            found.add(day)
        if found != set(range(1, days + 1)):
            raise ValueError(f"{civil_year}-{month:02}: 日付欄の欠落があります")
        for column, entries in anchors.items():
            entries.sort()
            for i, (y, day) in enumerate(entries):
                left = 41.5 + column * 135.6
                bottom = min(y + 109, entries[i + 1][0] - 4 if i + 1 < len(entries)
                             else offset + 771, (773 if half == 0 else 1484))
                rect = pymupdf.Rect(left, y - 4, left + 135.6, bottom)
                iso = date(civil_year, month, day).isoformat()
                evidence = extract_cell(page, rect, text, placed_images, filled)
                cells.append({"date": iso, "bbox": [rect.x0, rect.y0, rect.x1, rect.y1], **evidence})
    return {"page": index + 1, "drawings": len(drawings), "images": len(images),
            "cells": sorted(cells, key=lambda cell: cell["date"])}


def extract_cell(page, rect, text, images, filled):
    import pymupdf

    rows = sorted((s for s in text if pymupdf.Point(*s["bbox"][:2]) in rect),
                  key=lambda s: (round(s["bbox"][1] / 3), s["bbox"][0]))
    labels = {normalize(s["text"]) for s in rows}
    small_text = [s["text"] for s in rows if s["size"] < 8 and re.search("ShinGo|GothicBBB", s["font"])]
    icons = {digest for center, digest, _ in images if center in rect}
    graphics = sum(rect.x0 <= x0 <= x1 <= rect.x1 and rect.y0 <= y0 <= y1 <= rect.y1
                   for x0, y0, x1, y1 in filled)
    if "クリーンセン" in labels and "ター休日受入" in labels:
        labels.add("クリーンセンター休日受入")
    missing_labels = any(digest in icons and item not in labels
                         for digest, item in LABELED_ICONS.items())
    unfamiliar = any(normalize(value) not in ITEMS | KNOWN_FRAGMENTS for value in small_text)
    unknown_icons = {digest for center, digest, bbox in images if center in rect
                     and 10 <= bbox.width <= 60 and 10 <= bbox.height <= 70
                     and digest not in BURNABLE | NORTH_ICONS.keys() | LABELED_ICONS.keys()}
    return {
        "text": [s["text"] for s in rows], "small_text": small_text,
        "image_digests": sorted(icons), "unknown_images": sorted(unknown_icons),
        "filled_paths": graphics,
        "ocr": ocr_cell(page, rect) if unfamiliar or unknown_icons or missing_labels else "",
    }


def ocr_cell(page, rect):
    import subprocess

    import pymupdf

    try:
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=rect)
        result = subprocess.run(["tesseract", "stdin", "stdout", "-l", "jpn", "--psm", "11"],
                                input=pixmap.tobytes("png"), capture_output=True, timeout=30,
                                check=True)
        return result.stdout.decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"OCR実行不可: {exc}"
