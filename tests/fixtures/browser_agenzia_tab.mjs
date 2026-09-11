import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";

function nameMatches(actual, requested) {
  if (requested == null) return true;
  if (requested instanceof RegExp) return requested.test(actual);
  return actual.includes(requested);
}

class FakeLocator {
  constructor(site, role, name, indices = null) {
    this.site = site;
    this.role = role;
    this.name = name;
    this.indices = indices;
  }

  matches() {
    const controls = this.site.controls().filter(
      (control) => control.role === this.role && nameMatches(control.name, this.name)
    );
    return this.indices == null ? controls : this.indices.map((index) => controls[index]).filter(Boolean);
  }

  async count() {
    return this.matches().length;
  }

  nth(index) {
    return new FakeLocator(this.site, this.role, this.name, [index]);
  }

  async click() {
    const [control] = this.matches();
    if (!control) throw new Error("missing fake control");
    await control.click?.();
  }

  async fill(value) {
    const [control] = this.matches();
    if (!control) throw new Error("missing fake control");
    control.fill(value);
  }

  async getAttribute(attribute) {
    const [control] = this.matches();
    return control?.attributes?.[attribute] ?? null;
  }

  async evaluate(callback) {
    const [control] = this.matches();
    if (!control) throw new Error("missing fake control");
    return callback(control.element);
  }
}

export class FakeAgenziaTab {
  constructor(downloadDirectory, { pages = 1, rows = 2, failRow = null, sameDetailUrl = false, loseTabAfterDownload = false } = {}) {
    this.loseTabAfterDownload = loseTabAfterDownload;
    this.lost = false;
    this.page = 0;
    this.pages = pages;
    this.rows = rows;
    this.failRow = failRow;
    this.sameDetailUrl = sameDetailUrl;
    this.downloadDirectory = downloadDirectory;
    this.state = "home";
    this.direction = null;
    this.row = null;
    this.serial = 0;
    this.eventResolver = null;
    this.filled = {};
    this.playwright = {
      getByRole: (role, options = {}) => new FakeLocator(this, role, options.name),
      waitForTimeout: async () => {},
      waitForEvent: async (event) => {
        assert.equal(event, "download");
        return new Promise((resolve) => {
          this.eventResolver = resolve;
        });
      }
    };
  }

  async url() {
    if (this.lost) throw new Error("No tab with id: private-lost-tab");
    const suffix = this.state === "detail" ? `/detail/${this.direction}/${this.sameDetailUrl ? "same" : `${this.page}/${this.row}`}` : `/${this.state}`;
    return `https://ivaservizi.agenziaentrate.gov.it${suffix}`;
  }

  controls() {
    const controls = [
      {
        role: "link",
        name: "Home consultazione",
        click: async () => {
          this.state = "home";
        }
      }
    ];

    if (this.state === "home") {
      for (const [direction, name] of [
        ["active", "Le tue fatture emesse"],
        ["passive", "Le tue fatture ricevute"]
      ]) {
        controls.push({
          role: "link",
          name,
          click: async () => {
            this.direction = direction;
            this.page = 0;
            this.state = "search";
          }
        });
      }
    }

    if (this.state === "search") {
      controls.push(
        { role: "textbox", name: "Dal:", fill: (value) => (this.filled.from = value) },
        { role: "textbox", name: "Al:", fill: (value) => (this.filled.to = value) },
        { role: "button", name: "Cerca", click: async () => (this.state = "list") }
      );
    }

    if (this.state === "list") {
      for (let index = 0; index < this.rows; index += 1) {
        controls.push({
          role: "link",
          name: `Dettaglio fattura private-${index}`,
          attributes: { href: `/detail/${this.direction}/${this.page}/${index}` },
          click: async () => {
            if (index === this.failRow) throw new Error("No tab with id: synthetic-private-tab");
            this.row = index;
            this.state = "detail";
          }
        });
      }
      controls.push({
        role: "link",
        name: "Pagina successiva",
        element: {
          parentElement: { className: this.page + 1 < this.pages ? "" : "disabled" },
          getAttribute: () => null
        },
        click: async () => {
          this.page += 1;
        }
      });
    }

    if (this.state === "detail") {
      controls.push(
        {
          role: "button",
          name: "download file fattura",
          click: async () => {
            const filename = `invoice-${this.direction}-${this.row}-${this.serial++}.xml`;
            await writeFile(join(this.downloadDirectory, filename), "fixture");
            this.eventResolver?.({ suggestedFilename: filename });
            this.eventResolver = null;
            this.lost = this.loseTabAfterDownload;
          }
        },
        {
          role: "link",
          name: "Torna alla pagina precedente",
          click: async () => {
            this.state = "list";
          }
        }
      );
    }

    return controls;
  }
}
