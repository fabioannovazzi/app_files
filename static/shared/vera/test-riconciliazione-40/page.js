"use strict";

const rows = [...document.querySelectorAll("tbody tr")];
const buttons = [...document.querySelectorAll("[data-filter]")];
const search = document.querySelector("#search");
const count = document.querySelector("#count");
let filter = "all";

function normalize(value) {
  return value.toLocaleLowerCase("it").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function update() {
  const term = normalize(search.value.trim());
  let visible = 0;
  rows.forEach((row) => {
    const matchesFilter = filter === "all" || row.dataset.state === "pending";
    row.hidden = !(matchesFilter && normalize(row.textContent).includes(term));
    if (!row.hidden) visible += 1;
  });
  count.textContent = visible === 1 ? "1 prova mostrata" : `${visible} prove mostrate`;
  document.querySelector("#empty").hidden = visible > 0;
}

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    filter = button.dataset.filter;
    buttons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    update();
  });
});
search.addEventListener("input", update);
document.querySelector(".controls").hidden = false;
count.hidden = false;
