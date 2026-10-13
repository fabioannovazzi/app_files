"use strict";
// Embedded in the legal/tax widgets; source and origin checks protect review writes.
(() => {
  const pending = new Map(), listeners = new Set();
  let sequence = 0, initialized = false, origin = null;
  const framed = Boolean(window.parent && window.parent !== window);
  function request(method, params, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const id = `review-ui-${++sequence}`;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Review host did not respond to ${method}.`));
      }, timeout);
      pending.set(id, { resolve, reject, timer });
      window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, origin || "*");
    });
  }
  window.addEventListener("message", (event) => {
    if (!framed || event.source !== window.parent || (origin && event.origin !== origin)) return;
    const message = event.data;
    if (!message || message.jsonrpc !== "2.0") return;
    const entry = pending.get(message.id);
    if (entry) {
      // Pin the actual parent after our initialization response, before any case data.
      origin = event.origin;
      clearTimeout(entry.timer);
      pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message || "Review host request failed."));
      else entry.resolve(message.result);
      return;
    }
    if (origin && message.method === "ui/notifications/tool-result") {
      for (const listener of listeners) listener(message.params);
    }
  });
  const ready = framed ? request("ui/initialize", {
    protocolVersion: "2026-01-26",
    appInfo: { name: "Mparanza legal and tax review", version: "1.0.0" },
    appCapabilities: {},
  }, 15000).then(() => {
    initialized = true;
    window.parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, origin);
    window.dispatchEvent(new Event("mparanza:review-host-ready"));
    return true;
  }).catch(() => false) : Promise.resolve(false);
  window.mparanzaReviewHost = {
    canCallTools: () => initialized || typeof window.openai?.callTool === "function",
    async callTool(name, args) {
      if (await ready) return request("tools/call", { name, arguments: args });
      if (typeof window.openai?.callTool === "function") return window.openai.callTool(name, args);
      throw new Error("Review host is unavailable. Keep decisions pending or export them for fallback review.");
    },
    onToolResult: (listener) => listeners.add(listener),
  };
})();
