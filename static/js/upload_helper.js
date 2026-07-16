(() => {
  /**
   * Wire a clickable card to a hidden file input and optional label.
   * @param {Object} options
   * @param {string} options.cardSelector - CSS selector for the upload card(s).
   * @param {HTMLInputElement} options.inputEl - The hidden file input element.
   * @param {HTMLElement} [options.labelEl] - Element to display the selected file name.
   * @param {string} [options.noFileText="No file selected"] - Text to show when no file is selected.
   * @param {(file: File | null) => void} [options.onFile] - Callback invoked on selection change.
   */
  function bindUploadCard({ cardSelector, inputEl, labelEl, noFileText = "No file selected", onFile }) {
    if (!inputEl) {
      console.error("bindUploadCard: input element is required");
      return;
    }

    const setLabel = (text) => {
      if (labelEl) {
        labelEl.textContent = text;
      }
    };

    if (cardSelector) {
      document.querySelectorAll(cardSelector).forEach((card) => {
        card.addEventListener("click", () => inputEl.click());
      });
    }

    inputEl.addEventListener("change", () => {
      const file = inputEl.files && inputEl.files[0] ? inputEl.files[0] : null;
      setLabel(file ? file.name : noFileText);
      if (typeof onFile === "function") {
        onFile(file);
      }
    });
  }

  window.bindUploadCard = bindUploadCard;
})();
