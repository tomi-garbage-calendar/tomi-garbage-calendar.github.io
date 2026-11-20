const messages = {
  ja: {
    title: "東御市ごみ出しカレンダー",
    district: "お住まいの地区",
    choose: "地区を選択してください",
    today: "今日",
    tomorrow: "明日",
    dayAfter: "明後日",
    dayPicker: "確認する日",
    districtLinks: "地区のカレンダー",
    loading: "読み込み中…",
    empty: "ごみ出し・資源回収の予定はありません。",
    unavailable: "この日のカレンダーはまだ公開されていません。",
    error: "カレンダーを読み込めませんでした。",
    retry: "もう一度読み込む",
    fullCalendar: "年間の収集予定",
    ics: "ICSで購読",
    unofficial: "このサイトは東御市の非公式サイトです。",
    official: "東御市公式カレンダー",
  },
};

const locale = Object.hasOwn(messages, document.documentElement.lang)
  ? document.documentElement.lang : "ja";
const text = messages[locale];
const district = document.querySelector("#district");
const buttons = [...document.querySelectorAll("[data-day]")];
const dateLabel = document.querySelector("#date");
const status = document.querySelector("#status");
const items = document.querySelector("#items");
const retry = document.querySelector("#retry");
const links = document.querySelector("#district-links");
const dayPicker = document.querySelector(".day-picker");
const storageKey = "tomi-garbage-calendar.district";
const svgNamespace = "http://www.w3.org/2000/svg";
const tokyoDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Tokyo", calendar: "gregory", numberingSystem: "latn",
  year: "numeric", month: "2-digit", day: "2-digit",
});
const displayDate = new Intl.DateTimeFormat(locale, {
  timeZone: "UTC", year: "numeric", month: "long", day: "numeric", weekday: "long",
});

let manifest;
let offset = 0;
let renderVersion = 0;
let displayedToday;
const calendars = new Map();

if (document.documentElement.lang !== "ja") {
  for (const element of document.querySelectorAll("[data-text]")) {
    element.textContent = text[element.dataset.text];
  }
  document.title = text.title;
}
dayPicker.setAttribute("aria-label", text.dayPicker);
links.setAttribute("aria-label", text.districtLinks);

function todayInTomi() {
  const parts = Object.fromEntries(tokyoDate.formatToParts().map(({ type, value }) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

async function readJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function setStatus(key) {
  status.hidden = !key;
  status.textContent = key ? text[key] : "";
  retry.hidden = key !== "error";
}

function calendarFor(year, area) {
  const url = manifest.districtFiles ? `data/${year}/${area}.json` : `data/${year}.json`;
  if (!calendars.has(url)) {
    calendars.set(url, readJson(url).catch((error) => {
      calendars.delete(url);
      throw error;
    }));
  }
  return calendars.get(url);
}

async function render() {
  const version = ++renderVersion;
  displayedToday = todayInTomi();
  const date = new Date(`${displayedToday}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  const day = date.toISOString().slice(0, 10);
  dateLabel.dateTime = day;
  dateLabel.textContent = displayDate.format(date);

  items.replaceChildren();
  items.hidden = true;
  links.hidden = !district.value;
  if (!manifest) {
    setStatus(status.textContent === text.error ? "error" : "loading");
    return;
  }
  const area = district.value;
  if (!area) {
    setStatus("choose");
    return;
  }
  document.querySelector("#calendar-link").href = `${area}.html`;
  document.querySelector("#ics-link").href = `${area}.ics`;
  const year = date.getUTCFullYear() - Number(date.getUTCMonth() < 3);
  if (!manifest.years.includes(year)) {
    setStatus("unavailable");
    return;
  }
  setStatus("loading");
  try {
    const calendar = await calendarFor(year, area);
    if (version !== renderVersion) return;
    const events = calendar.events.filter((event) => event.district === area && event.date === day);
    for (const event of events) {
      const item = document.createElement("li");
      const iconId = manifest.itemIcons?.[event.item_id] ?? manifest.itemIcons?.[event.item];
      if (typeof iconId === "string") {
        const icon = document.createElementNS(svgNamespace, "svg");
        icon.classList.add("collection-icon");
        icon.setAttribute("aria-hidden", "true");
        const drawing = document.createElementNS(svgNamespace, "use");
        drawing.setAttribute("href", `collection-icons.svg#${iconId}`);
        icon.append(drawing);
        item.append(icon);
      }
      const label = document.createElement("span");
      label.textContent = event.item;
      const details = document.createElement("div");
      details.append(label);
      const locationName = manifest.locationNames?.[event.location_type];
      if (locationName) {
        const location = document.createElement("button");
        location.type = "button";
        location.className = "collection-location";
        location.dataset.location = event.location_type;
        location.dataset.item = event.item;
        location.setAttribute("aria-haspopup", "dialog");
        location.textContent = locationName;
        details.append(location);
      }
      item.append(details);
      items.append(item);
    }
    items.hidden = events.length === 0;
    setStatus(events.length ? null : "empty");
  } catch {
    if (version === renderVersion) setStatus("error");
  }
}

async function initialize() {
  setStatus("loading");
  try {
    manifest = await readJson("data/index.json");
    for (const [id, name] of Object.entries(manifest.districts)) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = name;
      district.append(option);
    }
    district.disabled = false;
    try {
      const saved = localStorage.getItem(storageKey);
      if (Object.hasOwn(manifest.districts, saved)) district.value = saved;
    } catch {
      // District selection still works when storage is blocked.
    }
    render();
  } catch {
    manifest = undefined;
    setStatus("error");
  }
}

district.addEventListener("change", () => {
  try {
    localStorage.setItem(storageKey, district.value);
  } catch {
    // A failed write does not affect the current selection.
  }
  render();
});

for (const button of buttons) {
  button.addEventListener("click", () => {
    offset = Number(button.dataset.day);
    for (const choice of buttons) choice.setAttribute("aria-pressed", String(choice === button));
    render();
  });
}

retry.addEventListener("click", () => (manifest ? render() : initialize()));
function refreshDate() {
  if (displayedToday !== todayInTomi()) render();
}
document.addEventListener("visibilitychange", refreshDate);
setInterval(refreshDate, 30_000);
render();
initialize();
