(() => {
  const button = document.querySelector("[data-copy-prompt]");
  const prompt = document.getElementById("prompt-text");
  const status = document.getElementById("copy-status");
  if (!button || !prompt || !status) return;

  button.hidden = false;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(prompt.textContent.trim());
      status.textContent = "Prompt copiato. Puoi incollarlo in una nuova chat con Vera.";
    } catch {
      prompt.closest("details").open = true;
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(prompt);
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = "Copia automatica non disponibile. Il testo è selezionato: copialo oppure scarica il file TXT.";
    }
  });
})();
