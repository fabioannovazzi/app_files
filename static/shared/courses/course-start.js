"use strict";
const copyButton = document.getElementById("course-start-copy");
const requestField = document.getElementById("course-start-request");
const copyStatus = document.getElementById("course-start-status");
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
