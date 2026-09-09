(() => {
  const OPEN_CLASS = "custom-select--open";
  let openInstance = null;
  let idCounter = 0;

  function enhance(select) {
    if (
      !(select instanceof HTMLSelectElement) ||
      select.multiple ||
      select.size > 1 ||
      select.dataset.nativeSelect === "true" ||
      select.dataset.customSelect === "true"
    ) {
      return;
    }

    select.dataset.customSelect = "true";

    const parent = select.parentElement;
    if (!parent) {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "custom-select";

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "custom-select__button";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("role", "combobox");

    const list = document.createElement("ul");
    list.className = "custom-select__list";
    list.setAttribute("role", "listbox");
    list.tabIndex = -1;

    const listId = `custom-select-list-${++idCounter}`;
    list.id = listId;
    trigger.setAttribute("aria-controls", listId);

    const buttonLabel = document.createElement("span");
    buttonLabel.className = "custom-select__label";
    trigger.appendChild(buttonLabel);

    parent.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    wrapper.appendChild(trigger);
    wrapper.appendChild(list);

    select.classList.add("custom-select__input");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    const state = {
      select,
      wrapper,
      trigger,
      list,
      buttonLabel,
      options: [],
      isOpen: false,
      focusedIndex: -1,
    };

    buildOptions(state);
    syncSelection(state);
    refreshDisabledState(state);

    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      toggleList(state);
    });

    trigger.addEventListener("keydown", (event) => handleTriggerKeydown(event, state));
    list.addEventListener("keydown", (event) => handleListKeydown(event, state));

    list.addEventListener("click", (event) => {
      const optionEl = event.target.closest("[data-index]");
      if (!optionEl || optionEl.getAttribute("aria-disabled") === "true") {
        return;
      }
      event.preventDefault();
      selectOption(state, Number(optionEl.dataset.index));
    });

    list.addEventListener("mousemove", (event) => {
      const optionEl = event.target.closest("[data-index]");
      if (!optionEl || optionEl.getAttribute("aria-disabled") === "true") {
        return;
      }
      setActiveIndex(state, Number(optionEl.dataset.index), false);
    });

    select.addEventListener("change", () => syncSelection(state));

    const form = select.closest("form");
    if (form) {
      form.addEventListener("reset", () => {
        window.requestAnimationFrame(() => syncSelection(state));
      });
    }

    const observer = new MutationObserver((mutations) => {
      let shouldRebuild = false;
      let shouldSyncDisabled = false;

      mutations.forEach((mutation) => {
        if (mutation.type === "childList") {
          shouldRebuild = true;
        }
        if (mutation.type === "attributes" && mutation.attributeName === "disabled") {
          shouldSyncDisabled = true;
        }
      });

      if (shouldRebuild) {
        buildOptions(state);
      }
      if (shouldRebuild || shouldSyncDisabled) {
        syncSelection(state);
        refreshDisabledState(state);
      }
    });

    observer.observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["disabled", "label"],
    });
  }

  function buildOptions(state) {
    const { select, list } = state;
    state.options = [];
    list.innerHTML = "";

    Array.from(select.options).forEach((option, index) => {
      const item = document.createElement("li");
      item.className = "custom-select__option";
      item.dataset.index = String(index);
      item.setAttribute("role", "option");
      item.textContent = option.textContent;

      if (option.disabled || option.hidden) {
        item.setAttribute("aria-disabled", "true");
        item.classList.add("is-disabled");
      }

      if (!option.value && option.dataset.placeholder === "true") {
        item.classList.add("is-placeholder");
      }

      list.appendChild(item);
      state.options.push(item);
    });
  }

  function syncSelection(state) {
    const { select, buttonLabel, options } = state;
    const selectedIndex = select.selectedIndex;
    const selectedOption = select.options[selectedIndex];
    const text = selectedOption ? selectedOption.textContent : select.getAttribute("data-placeholder") || "Select…";
    buttonLabel.textContent = text || "";

    options.forEach((optionEl, index) => {
      const isSelected = index === selectedIndex;
      optionEl.classList.toggle("is-selected", isSelected);
      if (isSelected) {
        optionEl.setAttribute("aria-selected", "true");
        state.focusedIndex = index;
      } else {
        optionEl.removeAttribute("aria-selected");
      }
    });
  }

  function refreshDisabledState(state) {
    const disabled = state.select.disabled;
    state.trigger.disabled = disabled;
    state.wrapper.classList.toggle("custom-select--disabled", disabled);
  }

  function toggleList(state) {
    if (state.select.disabled) {
      return;
    }
    if (state.isOpen) {
      closeList(state);
    } else {
      openList(state);
    }
  }

  function openList(state) {
    if (openInstance && openInstance !== state) {
      closeList(openInstance, false);
    }

    state.isOpen = true;
    openInstance = state;
    state.wrapper.classList.add(OPEN_CLASS);
    state.trigger.setAttribute("aria-expanded", "true");

    const initialIndex = state.select.selectedIndex >= 0 ? state.select.selectedIndex : 0;
    setActiveIndex(state, initialIndex, false);
  }

  function closeList(state, focusTrigger = true) {
    if (!state.isOpen) {
      return;
    }
    state.isOpen = false;
    if (openInstance === state) {
      openInstance = null;
    }
    state.wrapper.classList.remove(OPEN_CLASS);
    state.trigger.setAttribute("aria-expanded", "false");
    if (focusTrigger) {
      state.trigger.focus();
    }
  }

  function setActiveIndex(state, nextIndex, ensureVisible = true) {
    if (nextIndex < 0 || nextIndex >= state.options.length) {
      return;
    }
    const optionEl = state.options[nextIndex];
    if (!optionEl || optionEl.getAttribute("aria-disabled") === "true") {
      return;
    }

    state.options.forEach((el) => el.classList.remove("is-active"));
    optionEl.classList.add("is-active");
    state.focusedIndex = nextIndex;

    if (ensureVisible) {
      const optionRect = optionEl.getBoundingClientRect();
      const listRect = state.list.getBoundingClientRect();
      if (optionRect.top < listRect.top) {
        state.list.scrollTop -= listRect.top - optionRect.top + 4;
      } else if (optionRect.bottom > listRect.bottom) {
        state.list.scrollTop += optionRect.bottom - listRect.bottom + 4;
      }
    }
  }

  function moveFocus(state, direction) {
    if (!state.options.length) {
      return;
    }

    let nextIndex = state.focusedIndex;
    do {
      nextIndex = (nextIndex + direction + state.options.length) % state.options.length;
      const optionEl = state.options[nextIndex];
      if (optionEl && optionEl.getAttribute("aria-disabled") !== "true") {
        setActiveIndex(state, nextIndex);
        break;
      }
    } while (nextIndex !== state.focusedIndex);
  }

  function selectOption(state, index) {
    if (index < 0 || index >= state.select.options.length) {
      return;
    }
    const targetOption = state.select.options[index];
    if (!targetOption || targetOption.disabled || targetOption.hidden) {
      return;
    }
    state.select.selectedIndex = index;
    state.select.dispatchEvent(new Event("change", { bubbles: true }));
    closeList(state);
  }

  function handleTriggerKeydown(event, state) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!state.isOpen) {
          openList(state);
        }
        moveFocus(state, 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        if (!state.isOpen) {
          openList(state);
        }
        moveFocus(state, -1);
        break;
      case "Home":
        event.preventDefault();
        openList(state);
        setActiveIndex(state, 0);
        break;
      case "End":
        event.preventDefault();
        openList(state);
        setActiveIndex(state, state.options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (!state.isOpen) {
          openList(state);
        } else {
          selectOption(state, state.focusedIndex);
        }
        break;
      case "Escape":
        if (state.isOpen) {
          event.preventDefault();
          closeList(state);
        }
        break;
      default:
        handleTypeAhead(event, state);
        break;
    }
  }

  function handleListKeydown(event, state) {
    if (!state.isOpen) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeList(state);
    }
  }

  function handleTypeAhead(event, state) {
    if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }
    const searchChar = event.key.toLowerCase();
    const currentIndex = state.focusedIndex >= 0 ? state.focusedIndex : 0;
    const total = state.options.length;
    for (let offset = 1; offset <= total; offset += 1) {
      const candidateIndex = (currentIndex + offset) % total;
      const optionEl = state.options[candidateIndex];
      if (!optionEl || optionEl.getAttribute("aria-disabled") === "true") {
        continue;
      }
      if (optionEl.textContent.trim().toLowerCase().startsWith(searchChar)) {
        setActiveIndex(state, candidateIndex);
        break;
      }
    }
  }

  function enhanceExistingSelects() {
    document.querySelectorAll("select:not([multiple]):not([data-native-select])").forEach(enhance);
  }

  function handleDocumentClick(event) {
    const target = event.target;
    if (!openInstance || !target) {
      return;
    }
    if (!openInstance.wrapper.contains(target)) {
      closeList(openInstance, false);
    }
  }

  function observeNewSelects() {
    const rootObserver = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof HTMLElement)) {
            return;
          }
          if (node.matches && node.matches("select:not([multiple]):not([data-native-select])")) {
            enhance(node);
          }
          node.querySelectorAll &&
            node.querySelectorAll("select:not([multiple]):not([data-native-select])").forEach(enhance);
        });
      });
    });

    rootObserver.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && openInstance) {
      closeList(openInstance);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      enhanceExistingSelects();
      observeNewSelects();
    });
  } else {
    enhanceExistingSelects();
    observeNewSelects();
  }
})();
