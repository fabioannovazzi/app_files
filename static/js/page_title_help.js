(() => {
  const helps = Array.from(document.querySelectorAll("[data-page-help]"));
  if (!helps.length) {
    return;
  }

  const closeHelp = (help) => {
    help.classList.remove("is-open");
    const button = help.querySelector(".page-title-help__button");
    if (button) {
      button.setAttribute("aria-expanded", "false");
    }
  };

  const openHelp = (help) => {
    help.classList.add("is-open");
    const button = help.querySelector(".page-title-help__button");
    if (button) {
      button.setAttribute("aria-expanded", "true");
    }
  };

  helps.forEach((help) => {
    const button = help.querySelector(".page-title-help__button");
    if (!button) {
      return;
    }

    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (help.classList.contains("is-open")) {
        closeHelp(help);
        button.blur();
        return;
      }
      helps.forEach((entry) => {
        if (entry !== help) {
          closeHelp(entry);
        }
      });
      openHelp(help);
    });
  });

  document.addEventListener("click", (event) => {
    helps.forEach((help) => {
      if (!help.contains(event.target)) {
        closeHelp(help);
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      helps.forEach(closeHelp);
    }
  });
})();
