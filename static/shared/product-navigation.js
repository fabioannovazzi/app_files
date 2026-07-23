(() => {
  const disclosureSelector = "[data-product-nav-disclosure]";
  const disclosures = [...document.querySelectorAll(disclosureSelector)];
  const menu = document.querySelector("[data-product-nav-menu]");
  const menuTrigger = menu?.querySelector("[data-product-nav-menu-trigger]");

  function closeMenu() {
    if (!menu || !menuTrigger) return;
    menu.removeAttribute("data-menu-open");
    menuTrigger.setAttribute("aria-expanded", "false");
  }

  function closeDisclosures(except = null) {
    disclosures.forEach((disclosure) => {
      if (disclosure !== except) disclosure.removeAttribute("open");
    });
  }

  menuTrigger?.addEventListener("click", () => {
    const willOpen = !menu.hasAttribute("data-menu-open");
    closeDisclosures();
    menu.toggleAttribute("data-menu-open", willOpen);
    menuTrigger.setAttribute("aria-expanded", String(willOpen));
  });
  menu?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  disclosures.forEach((disclosure) => {
    disclosure.addEventListener("toggle", () => {
      if (disclosure.open) {
        closeMenu();
        closeDisclosures(disclosure);
      }
    });
    disclosure.querySelectorAll("a, button[data-lang]").forEach((control) => {
      control.addEventListener("click", () => disclosure.removeAttribute("open"));
    });
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-product-nav-menu]")) closeMenu();
    if (!event.target.closest(disclosureSelector)) closeDisclosures();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const menuWasOpen = menu?.hasAttribute("data-menu-open");
      const openDisclosure = disclosures.find((disclosure) => disclosure.open);
      closeMenu();
      closeDisclosures();
      if (menuWasOpen) {
        menuTrigger?.focus();
      } else {
        openDisclosure?.querySelector("summary")?.focus();
      }
    }
  });
})();
