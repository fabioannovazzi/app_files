(() => {
  "use strict";

  const form = document.getElementById("voiceForm");
  const fileInput = document.getElementById("requestFile");
  const summary = document.getElementById("requestSummary");
  const button = document.getElementById("generateButton");
  const status = document.getElementById("status");
  let approvedRequest = null;

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.style.color = isError ? "#9b1c1c" : "#071d49";
  }

  function validateRequest(value) {
    if (!value || value.schema_version !== 1 || value.workflow !== "clara:research-video") {
      throw new Error("This is not a Clara Research Video voice request.");
    }
    if (!value.approval || value.approval.confirmed_by_user !== true) {
      throw new Error("The request does not contain explicit narration approval.");
    }
    if (!Array.isArray(value.scenes) || value.scenes.length < 1) {
      throw new Error("The request contains no narration scenes.");
    }
    return value;
  }

  fileInput.addEventListener("change", async () => {
    approvedRequest = null;
    button.disabled = true;
    setStatus("");
    const file = fileInput.files?.[0];
    if (!file) {
      summary.textContent = "Choose the approved request JSON created by Clara.";
      return;
    }
    try {
      const parsed = validateRequest(JSON.parse(await file.text()));
      approvedRequest = parsed;
      const characterCount = parsed.scenes.reduce(
        (total, scene) => total + String(scene.narration || "").length,
        0,
      );
      summary.textContent = `${parsed.scenes.length} scenes · ${parsed.language.toUpperCase()} · ${characterCount} narration characters`;
      button.disabled = false;
    } catch (error) {
      summary.textContent = error instanceof Error ? error.message : "The request could not be read.";
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!approvedRequest) return;
    button.disabled = true;
    setStatus("Generating narration…");
    try {
      const response = await fetch("/case-notes/api/research-video/voice", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Mparanza-Action": "research-video-voice-v1",
        },
        body: JSON.stringify(approvedRequest),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Narration generation failed (${response.status}).`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const matchedName = disposition.match(/filename="([^"]+)"/);
      const filename = matchedName?.[1] || "research-video-voice.zip";
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
      setStatus("Narration downloaded. Return to Clara to validate and render it.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Narration generation failed.", true);
    } finally {
      button.disabled = false;
    }
  });
})();
