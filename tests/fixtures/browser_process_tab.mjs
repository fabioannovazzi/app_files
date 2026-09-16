/** Synthetic browser binding for process lifecycle integration tests; never a live adapter. */
import { readFile } from "node:fs/promises";
import { executeProcess } from "../../plugins/browser-automation/scripts/process_runtime.mjs";

class Locator {
  constructor(tab, key, row = null) { this.tab = tab; this.key = key; this.row = row; }
  getByTestId(name) { return new Locator(this.tab, name, this.row ?? 0); }
  nth(index) { return new Locator(this.tab, this.key, index); }
  async count() { return this.key === "result-row" && this.row === null ? 2 : (await this.isVisible() ? 1 : 0); }
  async isVisible() {
    if (this.tab.fail && this.key === "result-row") return false;
    if (this.tab.empty && this.key === "result-row") return false;
    if (this.key === "status") return this.tab.empty;
    return true;
  }
  async isEnabled() { return this.isVisible(); }
  async waitFor() { if (!(await this.isVisible())) throw new Error("SYNTHETIC private-session-url must stay out of feedback"); }
  async innerText() {
    if (this.key === "status") return this.tab.empty ? "No records found" : "Ready";
    if (this.key === "date") return "2026-09-15";
    if (this.key === "sender") return `Synthetic sender ${this.row}`;
    return `Synthetic subject ${this.row}`;
  }
  async fill(value) { this.tab.query = value; }
  async press() {}
}

export class ProcessFixtureTab {
  constructor({ fail = false, empty = false } = {}) {
    this.fail = fail; this.empty = empty; this.currentUrl = "http://127.0.0.1:18765/";
    this.playwright = {
      getByLabel: name => new Locator(this, name),
      getByRole: name => new Locator(this, name),
      getByTestId: name => new Locator(this, name),
      waitForLoadState: async () => {}, waitForTimeout: async () => {},
    };
  }
  async goto(url) { this.currentUrl = url; }
  async url() { return this.currentUrl; }
}

// Launched by Python tests with a newly reconstructed host context every time.
if (process.argv[2]) {
  const config = JSON.parse(await readFile(process.argv[2], "utf8"));
  const result = await executeProcess({ ...config,
    tab: config.noTab ? undefined : new ProcessFixtureTab(config),
    inputs: config.inputs ?? { query: "synthetic", "max-results": 2 },
  });
  process.stdout.write(JSON.stringify(result));
}
