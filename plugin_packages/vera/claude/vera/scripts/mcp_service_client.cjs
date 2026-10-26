"use strict";

const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

// Exact JSON-RPC IDs correlate replies; this transport never interprets requests
// semantically and never retries a call whose side effects may have happened.
class ServiceClient {
  constructor(root, name, config, { env = process.env, notification = () => {}, request = () => {} } = {}) {
    if (config.command !== "node" || !Array.isArray(config.args))
      throw new Error(`Unsupported local service launcher: ${name}`);
    const expand = value => value.replaceAll("${PLUGIN_ROOT}", root)
      .replaceAll("${CLAUDE_PLUGIN_ROOT}", root).replaceAll("${CODEX_PLUGIN_ROOT}", root);
    this.name = name;
    this.sequence = 0;
    this.pending = new Map();
    this.error = null;
    this.closed = false;
    this.child = spawn(process.execPath, config.args.map(expand), {
      cwd: path.resolve(root, expand(config.cwd || ".")),
      env: { ...env, ...Object.fromEntries(Object.entries(config.env || {}).map(([k, v]) => [k, expand(v)])) },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.exited = new Promise(resolve => this.child.once("close", resolve));
    this.child.stderr.on("data", data => process.stderr.write(data));
    this.child.on("error", error => this.fail(error));
    this.child.stdin.on("error", error => this.fail(error));
    this.child.on("close", (code, signal) => this.fail(new Error(
      `${name} closed (${signal || code}); inspect any existing result before retrying work`,
    )));
    this.lines = readline.createInterface({ input: this.child.stdout, crlfDelay: Infinity });
    this.lines.on("line", line => {
      if (!line.trim()) return;
      let message;
      try { message = JSON.parse(line); }
      catch { this.fail(new Error(`Invalid JSON from ${name}`)); return; }
      if (!message || message.jsonrpc !== "2.0") { this.fail(new Error(`Invalid JSON-RPC from ${name}`)); return; }
      if (message.method) {
        if (message.id !== undefined) request(message);
        else notification(message);
        return;
      }
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      pending.resolve(message);
    });
  }

  fail(error) {
    this.error ||= error;
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(this.error);
    }
    this.pending.clear();
    this.close();
  }

  send(message) {
    if (this.error) throw this.error;
    if (this.closed) throw new Error(`${this.name} transport is closed`);
    this.child.stdin.write(JSON.stringify(message) + "\n");
  }

  call(method, params = {}, { timeout = 0, started = () => {} } = {}) {
    if (this.error) return Promise.reject(this.error);
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = timeout ? setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${this.name}: ${method} timed out`));
      }, timeout) : null;
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.send({ jsonrpc: "2.0", id, method, params });
        started(id);
      } catch (error) {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(error);
      }
    });
  }

  async initialize(params) {
    const reply = await this.call("initialize", params, { timeout: 10000 });
    if (reply.error || !reply.result?.serverInfo || !reply.result?.capabilities)
      throw new Error(`${this.name}: invalid initialize response`);
    this.send({ jsonrpc: "2.0", method: "notifications/initialized" });
    return reply.result;
  }

  close(signal) {
    if (this.closed) return;
    this.closed = true;
    this.child.stdin.end();
    // Native execution retains its existing signal/job ownership policy.
    if (signal && this.child.exitCode === null) this.child.kill(signal);
  }
}

module.exports = { ServiceClient };
