import re

from extract import (BURNABLE, DISTRICTS, ITEMS, KNOWN_FRAGMENTS, LABELED_ICONS,
                     NORTH_ICONS, RESOURCE_DISTRICTS, normalize)


ITEM_NAMES = {normalize(item): item for item in ITEMS}
ITEM_NAMES["ビン"] = "びん"
RESOURCE_LABEL = re.compile(r"資源回収\(([^()]+)\)(田中|滋野|祢津|和)地区")
RESOURCE_ITEMS = {
    **dict.fromkeys(("新聞", "新聞紙", "古紙", "新聞等", "新聞紙等", "古紙等", "紙類"), "資源回収（新聞等）"),
    **dict.fromkeys(("ペット等", "ペットボトル"), "資源回収（ペット等）"),
    **dict.fromkeys(("びん", "ビン", "瓶"), "資源回収（びん）"),
}
UNSCOPED_PAPER = {"新聞", "新聞紙", "古紙"}

# One label per item ID. A source category can cover several items.
PUBLIC_ITEMS = {
    "burnable": ("もやせるごみ", ("もやせるごみ",)),
    "food": ("生ごみ", ("生ごみ",)),
    "packaging": ("容器包装プラスチック", ("容器包装プラ",)),
    "plastic-products": ("容器包装外プラスチック", ("容器包装以外プラ",)),
    "soiled-packaging": ("汚れ容器包装プラスチック", ("汚れ容器包装プラ",)),
    "glass": ("ビン", ("びん", "資源回収（びん）")),
    "brown-glass": ("茶色ビン", ("茶色びん",)),
    "clear-glass": ("無色ビン", ("無色びん",)),
    "colored-glass": ("他色ビン", ("他色びん",)),
    "can": ("カン", ("カン",)),
    "pet-bottle": ("ペットボトル", ("ペットボトル", "資源回収（ペット等）")),
    "paper": ("古紙・段ボール", ("紙類", "紙類・衣類", "資源回収（新聞等）")),
    "clothes": ("衣類", ("衣類", "紙類・衣類")),
    "foam": ("食品トレー・発泡スチロール", ("トレー等", "資源回収（ペット等）")),
    "metal-ceramics": ("金物・陶器等", ("金物・陶器等",)),
    "hazardous": ("有害ごみ", ("有害ごみ",)),
    "clean-center": ("クリーンセンター休日受入", ("クリーンセンター休日受入",)),
}
SOURCE_ITEMS = {}
for item_id, (label, sources) in PUBLIC_ITEMS.items():
    for source in sources:
        SOURCE_ITEMS.setdefault(source, []).append((item_id, label))

GARBAGE_STATION_ITEMS = {
    "burnable", "food", "packaging", "plastic-products", "soiled-packaging",
    "glass", "brown-glass", "clear-glass", "colored-glass", "can",
}
LOCATION_NAMES = {"garbage-station": "ごみステーション", "stockyard": "ストックヤード"}


def publication_data(data):
    events = {}
    for event in data["events"]:
        source = event["item"]
        collection = "regular"
        if source in RESOURCE_ITEMS.values():
            collection = "district-recycling"
        elif source == "クリーンセンター休日受入":
            collection = "clean-center"
        for item_id, label in SOURCE_ITEMS[source]:
            key = (event["district"], event["date"], item_id, collection)
            location_type = "garbage-station" if item_id in GARBAGE_STATION_ITEMS else "stockyard"
            events[key] = {**event, "item": label, "item_id": item_id,
                           "collection_type": collection, "location_type": location_type}
    return {**data, "schema_version": 2, "events": [events[key] for key in sorted(events)]}


def normalize_cell(cell, edition):
    districts = DISTRICTS[edition]
    labels = [normalize(raw) for raw in cell["text"]]
    icons = set(cell["image_digests"])
    items = {ITEM_NAMES[label] for label in labels
             if label in ITEM_NAMES and not label.startswith("資源回収")}
    warnings = []
    scoped = set()
    if BURNABLE & icons:
        items.update(("もやせるごみ", "生ごみ"))
        if not cell["filled_paths"]:
            warnings.append("もやせるごみの絵柄に対応するベクター図形がありません")
    if {"クリーンセン", "ター休日受入"}.issubset(labels):
        items.add("クリーンセンター休日受入")
    missing = {item for digest, item in LABELED_ICONS.items() if digest in icons and item not in items}
    if missing:
        warnings.append(f"絵柄に対応するラベルがありません: {', '.join(sorted(missing))}")
    if "金物・陶器等" in items and edition == "kitamimaki":
        area = {key for digest, key in NORTH_ICONS.items() if digest in icons}
        joined = "".join(labels)
        caption = {key for key, value in districts.items() if normalize(value) in joined}
        if len(area) != 1 or (caption and area != caption) or not {"ト", "レー等"}.issubset(labels):
            warnings.append("北御牧の金物・陶器等、トレー等の対象区域を確認できません")
        else:
            scoped.update((key, item) for key in area for item in ("金物・陶器等", "トレー等"))
        items.difference_update(("金物・陶器等", "トレー等"))
    for raw, label in zip(cell["text"], labels):
        if label in UNSCOPED_PAPER:
            warnings.append(f"紙類の収集区分を確認してください: {raw}")
            continue
        if not label.startswith("資源回収"):
            continue
        match = RESOURCE_LABEL.fullmatch(label)
        item = RESOURCE_ITEMS.get(match[1]) if match else None
        targets = districts.keys() & RESOURCE_DISTRICTS[match[2]] if match else set()
        if item and targets:
            scoped.update((key, item) for key in targets)
        else:
            warnings.append(f"資源回収の表示を確認してください: {raw}")
    unfamiliar = []
    for raw in cell["small_text"]:
        label = normalize(raw)
        if (label not in ITEM_NAMES and label not in KNOWN_FRAGMENTS
                and label not in UNSCOPED_PAPER and not label.startswith("資源回収")):
            unfamiliar.append(raw)
    if unfamiliar:
        warnings.append(f"未対応の小型ラベル: {', '.join(unfamiliar)}")
    if cell["unknown_images"]:
        warnings.append(f"未対応の絵柄: {', '.join(cell['unknown_images'])}")
    return scoped | {(area, item) for area in districts for item in items}, warnings


def normalize_extraction(extraction):
    events = set()
    issues = []
    for page in extraction["pages"]:
        for cell in page["cells"]:
            day = cell["date"]
            items, warnings = normalize_cell(cell, extraction["edition"])
            events.update((area, day, item) for area, item in items)
            issues.extend(f"{page['page']}ページ {day}: {warning}" for warning in warnings)
    return {"events": sorted(events), "issues": issues}
