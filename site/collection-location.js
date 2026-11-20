const descriptions = new Map([
  ["garbage-station", "収集日に、お住まいの地区で指定されたごみステーションに出してください。"],
  ["stockyard", "利用できる場所や時間は、お住まいの地区の案内でご確認ください。"],
]);

const dialog = document.createElement("dialog");
dialog.className = "location-dialog";
dialog.setAttribute("aria-labelledby", "location-dialog-title");
dialog.innerHTML = `
  <h2 id="location-dialog-title"></h2>
  <p class="location-dialog-item"></p>
  <p class="location-dialog-description"></p>
  <form method="dialog"><button type="submit" autofocus>閉じる</button></form>
`;
document.body.append(dialog);

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-location]");
  if (!button) return;
  const description = descriptions.get(button.dataset.location);
  if (!description) return;
  dialog.querySelector("h2").textContent = button.textContent.trim();
  dialog.querySelector(".location-dialog-item").textContent = `対象品目：${button.dataset.item}`;
  dialog.querySelector(".location-dialog-description").textContent = description;
  dialog.showModal();
});
