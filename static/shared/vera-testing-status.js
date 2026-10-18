/* Testing levels are computed on the server from concluded pipeline runs. */
(function () {
  "use strict";
  const product = document.documentElement.dataset.testingProduct || "vera";
  if (!["vera", "clara", "lucia"].includes(product)) return;
  const states = new Set(["untried", "agent", "tried", "repeated"]);
  let loading = false;

  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`/api/${product}/testing-status`, {
        cache: "no-store", credentials: "omit", signal: controller.signal
      });
      if (!response.ok) throw new Error("Testing status unavailable");
      const data = await response.json();
      if (data.schema_version !== 1 || !data.pipelines ||
          typeof data.pipelines !== "object" || Array.isArray(data.pipelines) ||
          Object.values(data.pipelines).some(value => !states.has(value))) {
        throw new Error("Invalid testing status");
      }
      const indicators = [...document.querySelectorAll("[data-testing-pipeline]")];
      if (indicators.some(node => !Object.hasOwn(data.pipelines, node.dataset.testingPipeline))) {
        throw new Error("Incomplete testing status");
      }
      indicators.forEach(node => {
        node.dataset.testStatus = data.pipelines[node.dataset.testingPipeline];
      });
      document.documentElement.dataset.testingSource = "received";
      document.querySelector("[data-testing-unavailable]").hidden = true;
      document.dispatchEvent(new Event("vera-testing-status-updated"));
    } catch (_error) {
      // Preserve the last received states; an outage is not a counter reset.
      document.documentElement.dataset.testingSource = "unavailable";
      document.querySelector("[data-testing-unavailable]").hidden = false;
    } finally {
      clearTimeout(timeout);
      loading = false;
    }
  }

  refresh();
  setInterval(refresh, 60000);
  document.addEventListener("visibilitychange", refresh);
}());
