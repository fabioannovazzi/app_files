"use strict";
document.querySelectorAll("[data-copy-target]").forEach((copyButton) => {
  const requestField = document.getElementById(copyButton.dataset.copyTarget);
  const copyStatus = document.getElementById(copyButton.dataset.copyStatus);
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(requestField.value);
      copyStatus.textContent = copyButton.dataset.copied;
    } catch {
      requestField.focus();
      requestField.select();
      copyStatus.textContent = copyButton.dataset.fallback;
    }
  });
});
