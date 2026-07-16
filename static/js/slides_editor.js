(function () {

  const VIEW_MODES = {
    LIST: "list",
    STORYBOARD: "storyboard",
  };

  const state = {
    decks: [],
    currentDeckId: null,
    slides: [],
    sections: [],
    thumbnails: {},
    selectedSlideId: null,
    selectedSlideIds: [],
    selectionAnchorId: null,
    currentTagJobId: null,
    dirty: false,
    importing: false,
    uploading: false,
    concatenating: false,
    printing: false,
    tagging: false,
    printJobTimer: null,
    viewMode: VIEW_MODES.LIST,
    storyboardScale: 1,
    marquee: null,
  };

  const elements = {};

  const DEFAULT_PREVIEW_STYLE_BUNDLES = ["/static/css/app.css"];
  const DEFAULT_PREVIEW_SCRIPT_BUNDLES = [];
  const MIN_PREVIEW_SCALE = 0.1;
  const MAX_PREVIEW_SCALE = 3;
  const PREVIEW_SCALE_EPSILON = 0.01;
  const PREVIEW_CONTENT_MEASUREMENT_LIMIT = 250;
  const DEFAULT_ALLOWED_PREVIEW_ORIGINS = [
    window.location.origin,
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    "https://unpkg.com",
    "https://cdn.plot.ly",
    "https://www.gstatic.com",
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
  ];

  let previewConfig = null;
  let tooltipMessages = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    tooltipMessages = loadTooltipMessages();
    elements.deckSelect = document.getElementById("deckSelect");
    elements.slideList = document.getElementById("slideList");
    elements.titleInput = document.getElementById("titleHtmlInput");
    elements.bodyInput = document.getElementById("bodyHtmlInput");
    elements.previewFrame = document.getElementById("slidePreviewFrame");
    elements.previewFallback = document.getElementById("slidePreviewFallback");
    elements.previewTitle = document.querySelector(".slides-editor__preview-title");
    elements.previewBody = document.querySelector(".slides-editor__preview-body");
    elements.status = document.getElementById("slidesStatus");
    elements.tagSummary = document.getElementById("tagSummary");
    elements.addBtn = document.getElementById("addSlideBtn");
    elements.deleteBtn = document.getElementById("deleteSlideBtn");
    elements.saveBtn = document.getElementById("saveDeckBtn");
    elements.rewriteBtn = document.getElementById("rewriteSlideBtn");
    elements.tagSlidesBtn = document.getElementById("tagSlidesBtn");
    elements.importBtn = document.getElementById("importSlideBtn");
    elements.importDialog = document.getElementById("importDialog");
    elements.importDeckSelect = document.getElementById("importDeckSelect");
    elements.importSlideList = document.getElementById("importSlideList");
    elements.importCloseBtn = document.getElementById("importCloseBtn");
    elements.concatBtn = document.getElementById("concatDecksBtn");
    elements.concatDialog = document.getElementById("concatDialog");
    elements.concatCloseBtn = document.getElementById("concatCloseBtn");
    elements.concatDeckList = document.getElementById("concatDeckList");
    elements.concatDeckNameInput = document.getElementById("concatDeckNameInput");
    elements.concatConfirmBtn = document.getElementById("concatConfirmBtn");
    elements.printDeckBtn = document.getElementById("printDeckBtn");
    elements.storyboardGrid = document.getElementById("storyboardGrid");
    elements.storyboardPane = document.getElementById("storyboardWorkspace");
    elements.workspaceDetailPane = document.getElementById("workspaceDetailPane");
    elements.storyboardSelectionBanner = document.getElementById("storyboardSelectionBanner");
    elements.storyboardSelectionSummary = document.getElementById("storyboardSelectionSummary");
    elements.storyboardDeleteBtn = document.getElementById("storyboardDeleteBtn");
    elements.storyboardPromoteBtn = document.getElementById("storyboardPromoteBtn");
    elements.storyboardDemoteBtn = document.getElementById("storyboardDemoteBtn");
    elements.storyboardClearBtn = document.getElementById("storyboardClearBtn");
    elements.storyboardZoomInput = document.getElementById("storyboardZoomInput");
    elements.storyboardMarquee = document.getElementById("storyboardMarquee");
    elements.storyboardDirtyBanner = document.getElementById("storyboardDirtyBanner");
    elements.storyboardSaveBtn = document.getElementById("storyboardSaveBtn");
    elements.viewListBtn = document.getElementById("listViewBtn");
    elements.viewStoryboardBtn = document.getElementById("storyboardViewBtn");
    elements.sectionsList = document.getElementById("sectionsList");
    elements.addSectionBtn = document.getElementById("addSectionBtn");
    elements.uploadDeckBtn = document.getElementById("uploadDeckBtn");
    elements.uploadDeckZipBtn = document.getElementById("uploadDeckZipBtn");
    elements.prevSlideBtn = document.getElementById("prevSlideBtn");
    elements.nextSlideBtn = document.getElementById("nextSlideBtn");
    elements.bulkActionsBar = document.getElementById("bulkActionsBar");
    elements.bulkSelectionSummary = document.getElementById("bulkSelectionSummary");
    elements.bulkDeleteBtn = document.getElementById("bulkDeleteBtn");
    elements.bulkPromoteBtn = document.getElementById("bulkPromoteBtn");
    elements.bulkDemoteBtn = document.getElementById("bulkDemoteBtn");
    elements.bulkClearSelectionBtn = document.getElementById("bulkClearSelectionBtn");

    if (elements.printDeckBtn) {
      elements.printDeckBtn.disabled = true;
    }

    if (elements.previewFrame) {
      elements.previewFrame.addEventListener("load", handlePreviewFrameLoad);
    }

    previewConfig = createPreviewConfig();
    attachListeners();
    applyStoryboardScale(state.storyboardScale);
    updateTagButtonState();
    fetchDeckSummaries();
    resumeTagJobIfNeeded();
    window.addEventListener("beforeunload", handleBeforeUnload);
    updateViewToggle();
  }

  function attachListeners() {
    if (elements.deckSelect) {
      elements.deckSelect.addEventListener("change", (event) => {
        const deckId = event.target.value;
        if (deckId && deckId !== state.currentDeckId) {
          loadDeck(deckId);
        }
      });
    }

    elements.titleInput.addEventListener("input", () => {
      updateCurrentSlide("titleHtml", elements.titleInput.value);
    });
    elements.bodyInput.addEventListener("input", () => {
      updateCurrentSlide("bodyHtml", elements.bodyInput.value);
    });

    elements.addBtn.addEventListener("click", addSlideAfterCurrent);
    elements.deleteBtn.addEventListener("click", deleteCurrentSlide);
    elements.saveBtn.addEventListener("click", saveDeck);
    elements.rewriteBtn.addEventListener("click", rewriteCurrentSlide);
    if (elements.tagSlidesBtn) {
      elements.tagSlidesBtn.addEventListener("click", tagSlides);
    }
    elements.importBtn.addEventListener("click", openImportDialog);
    elements.importCloseBtn.addEventListener("click", closeImportDialog);
    if (elements.importDeckSelect) {
      elements.importDeckSelect.addEventListener("change", renderImportSlides);
    }
    if (elements.addSectionBtn) {
      elements.addSectionBtn.addEventListener("click", addSection);
    }
    if (elements.uploadDeckBtn) {
      elements.uploadDeckBtn.addEventListener("click", triggerDeckUpload);
    }
    if (elements.uploadDeckZipBtn) {
      elements.uploadDeckZipBtn.addEventListener("click", triggerDeckZipUpload);
    }
    if (elements.concatBtn) {
      elements.concatBtn.addEventListener("click", openConcatDialog);
    }
    if (elements.concatCloseBtn) {
      elements.concatCloseBtn.addEventListener("click", closeConcatDialog);
    }
    if (elements.concatConfirmBtn) {
      elements.concatConfirmBtn.addEventListener("click", handleConcatConfirm);
    }
    if (elements.printDeckBtn) {
      elements.printDeckBtn.addEventListener("click", handlePrintDeck);
    }
    if (elements.prevSlideBtn) {
      elements.prevSlideBtn.addEventListener("click", () => selectAdjacentSlide(-1));
    }
    if (elements.nextSlideBtn) {
      elements.nextSlideBtn.addEventListener("click", () => selectAdjacentSlide(1));
    }
    if (elements.viewListBtn) {
      elements.viewListBtn.addEventListener("click", () => setViewMode(VIEW_MODES.LIST));
    }
    if (elements.viewStoryboardBtn) {
      elements.viewStoryboardBtn.addEventListener("click", () => setViewMode(VIEW_MODES.STORYBOARD));
    }
    if (elements.bulkDeleteBtn) {
      elements.bulkDeleteBtn.addEventListener("click", deleteCurrentSlide);
    }
    if (elements.bulkPromoteBtn) {
      elements.bulkPromoteBtn.addEventListener("click", bulkPromoteSelectedSlides);
    }
    if (elements.bulkDemoteBtn) {
      elements.bulkDemoteBtn.addEventListener("click", bulkDemoteSelectedSlides);
    }
    if (elements.bulkClearSelectionBtn) {
      elements.bulkClearSelectionBtn.addEventListener("click", clearSlideSelection);
    }
    if (elements.storyboardDeleteBtn) {
      elements.storyboardDeleteBtn.addEventListener("click", deleteCurrentSlide);
    }
    if (elements.storyboardPromoteBtn) {
      elements.storyboardPromoteBtn.addEventListener("click", bulkPromoteSelectedSlides);
    }
    if (elements.storyboardDemoteBtn) {
      elements.storyboardDemoteBtn.addEventListener("click", bulkDemoteSelectedSlides);
    }
    if (elements.storyboardClearBtn) {
      elements.storyboardClearBtn.addEventListener("click", clearSlideSelection);
    }
    if (elements.storyboardZoomInput) {
      elements.storyboardZoomInput.addEventListener("input", handleStoryboardZoomInput);
    }
    if (elements.storyboardGrid) {
      elements.storyboardGrid.addEventListener("pointerdown", handleStoryboardPointerDown);
    }
    if (elements.storyboardSaveBtn) {
      elements.storyboardSaveBtn.addEventListener("click", saveDeck);
    }
    document.addEventListener("keydown", handleStoryboardKeyDown);
  }

  function handleBeforeUnload(event) {
    if (!state.dirty) {
      return undefined;
    }
    event.preventDefault();
    event.returnValue = "";
    return "";
  }

  function fetchDeckSummaries() {
    fetchJson("/slides/decks")
      .then((response) => {
        state.decks = (response.decks || []).map(normalizeDeckSummary);
        renderDeckOptions();
        if (state.decks.length) {
          const firstDeck = state.decks[0].deckId;
          loadDeck(firstDeck);
        }
      })
      .catch((error) => {
        reportStatus(`Failed to load deck list: ${error.message}`, true);
      });
  }

  function renderDeckOptions() {
    if (!elements.deckSelect) {
      return;
    }
    const previousValue = elements.deckSelect.value;
    elements.deckSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = getDeckPlaceholderLabel();
    placeholder.dataset.placeholder = "true";
    elements.deckSelect.appendChild(placeholder);
    state.decks.forEach((deck) => {
      const option = document.createElement("option");
      option.value = deck.deckId;
      option.textContent = deck.deckId;
      elements.deckSelect.appendChild(option);
    });
    const desiredValue = state.currentDeckId || previousValue || "";
    elements.deckSelect.value = desiredValue;
  }

  function getDeckPlaceholderLabel() {
    if (!elements.deckSelect) {
      return "Select deck";
    }
    return elements.deckSelect.getAttribute("data-placeholder") || "Select deck";
  }

  function updateDeckSummary(deck) {
    const existing = state.decks.find((entry) => entry.deckId === deck.deckId);
    if (existing) {
      existing.slides = deck.slides ? deck.slides.map(normalizeSlide) : [];
      existing.sections = deck.sections ? cloneSections(deck.sections) : [];
    } else {
      state.decks.push({
        deckId: deck.deckId,
        slides: deck.slides ? deck.slides.map(normalizeSlide) : [],
        sections: deck.sections ? cloneSections(deck.sections) : [],
      });
    }
  }

  function syncDeckSummary() {
    if (!state.currentDeckId) {
      return;
    }
    const entry = state.decks.find((deck) => deck.deckId === state.currentDeckId);
    if (!entry) {
      return;
    }
    entry.slides = state.slides.map((slide) => ({
      id: slide.id,
      titleHtml: slide.titleHtml,
      bodyHtml: slide.bodyHtml,
      notesHtml: slide.notesHtml,
      sourceHtml: slide.sourceHtml,
      fullHtml: slide.fullHtml,
      kind: slide.kind,
      sectionId: slide.sectionId,
      subsectionId: slide.subsectionId,
    }));
    entry.sections = cloneSections(state.sections);
  }

  function loadDeck(deckId) {
    reportStatus("Loading deck… semantic OCR may run via LLM, so this can take a moment.");
    return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}`)
      .then((deck) => {
        applyDeckResponse(deck);
        reportStatus(`Loaded deck ${deck.deckId}`);
        resumeTagJobIfNeeded(deck.deckId);
      })
      .catch((error) => {
        reportStatus(`Failed to load deck: ${error.message}`, true);
      });
  }

  function applyDeckResponse(deck) {
    if (!deck) {
      return;
    }
    state.currentDeckId = deck.deckId;
    updateDeckSummary(deck);
    state.slides = Array.isArray(deck.slides) ? deck.slides.map(normalizeSlide) : [];
    state.sections = Array.isArray(deck.sections) ? cloneSections(deck.sections) : [];
    state.thumbnails = deck.thumbnails || {};
    syncSectionHeaderSlides();
    state.selectedSlideId = state.slides.length ? state.slides[0].id : null;
    if (state.selectedSlideId) {
      state.selectedSlideIds = [state.selectedSlideId];
      state.selectionAnchorId = state.selectedSlideId;
    } else {
      state.selectedSlideIds = [];
      state.selectionAnchorId = null;
    }
    state.dirty = false;
    renderDeckOptions();
    if (elements.deckSelect) {
      elements.deckSelect.value = deck.deckId;
    }
    if (elements.printDeckBtn) {
      elements.printDeckBtn.disabled = !state.currentDeckId || state.printing;
    }
    updateTagButtonState();
    renderSelection();
  }

  function renderSlideList() {
    elements.slideList.innerHTML = "";
    const selectedSet = new Set(state.selectedSlideIds || []);
    state.slides.forEach((slide, index) => {
      const item = document.createElement("li");
      item.className = "slides-editor__list-item";
      const isSelected = selectedSet.has(slide.id);
      const isPrimary = slide.id === state.selectedSlideId;
      if (isSelected) {
        item.classList.add("is-selected");
      }
      if (isPrimary) {
        item.classList.add("is-active");
      }
      if (slide.kind === "sectionHeader") {
        item.classList.add("is-section-header");
      }
      item.draggable = true;
      item.dataset.slideId = slide.id;
      item.addEventListener("click", (event) => handleSlidePointer(event, slide.id));
      item.addEventListener("dragstart", handleDragStart);
      item.addEventListener("dragover", handleDragOver);
      item.addEventListener("drop", handleDrop);
      item.addEventListener("dragend", handleDragEnd);

      const label = document.createElement("span");
      label.textContent = `${index + 1}. ${getSlideLabel(slide)}`;

      const handle = document.createElement("span");
      handle.textContent = "↕";
      handle.setAttribute("aria-hidden", "true");

      item.appendChild(label);
      item.appendChild(handle);
      elements.slideList.appendChild(item);
    });
    elements.deleteBtn.disabled = state.selectedSlideIds.length === 0;
    const selectedSlide = getSelectedSlide();
    const hasSingleSelection = state.selectedSlideIds.length === 1;
    elements.rewriteBtn.disabled = !selectedSlide || selectedSlide.kind === "sectionHeader" || !hasSingleSelection;
    renderStoryboard();
    updateBulkActions();
    refreshDirtyIndicators();
  }

  let draggedSlideId = null;
  let storyboardDragId = null;
  let dragSelectionIds = [];

  function handleDragStart(event) {
    draggedSlideId = event.currentTarget.dataset.slideId;
    dragSelectionIds = buildDragSelectionIds(draggedSlideId);
    event.dataTransfer.effectAllowed = "move";
    event.currentTarget.classList.add("is-dragging");
  }

  function handleStoryboardDragStart(event) {
    storyboardDragId = event.currentTarget.dataset.slideId;
    dragSelectionIds = buildDragSelectionIds(storyboardDragId);
    event.dataTransfer.effectAllowed = "move";
    event.currentTarget.classList.add("is-dragging");
  }

  function handleStoryboardDragOver(event) {
    if (!storyboardDragId) {
      return;
    }
    event.preventDefault();
    const targetId = event.currentTarget.dataset.slideId;
    if (!targetId || targetId === storyboardDragId) {
      return;
    }
    event.currentTarget.classList.add("is-drop-target");
  }

  function handleStoryboardDrop(event) {
    event.preventDefault();
    const targetId = event.currentTarget.dataset.slideId;
    const sources = dragSelectionIds.length ? dragSelectionIds : storyboardDragId ? [storyboardDragId] : [];
    if (!sources.length || !targetId || sources.includes(targetId)) {
      return;
    }
    reorderSlides(sources, targetId);
  }

  function handleStoryboardDragEnd(event) {
    event.currentTarget.classList.remove("is-dragging");
    if (elements.storyboardGrid) {
      elements.storyboardGrid
        .querySelectorAll(".is-drop-target")
        .forEach((el) => el.classList.remove("is-drop-target"));
    }
    storyboardDragId = null;
    dragSelectionIds = [];
  }

  function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }

  function handleDrop(event) {
    event.preventDefault();
    const targetId = event.currentTarget.dataset.slideId;
    const sources = dragSelectionIds.length ? dragSelectionIds : draggedSlideId ? [draggedSlideId] : [];
    if (!sources.length || !targetId || sources.includes(targetId)) {
      return;
    }
    reorderSlides(sources, targetId);
  }

  function handleDragEnd(event) {
    event.currentTarget.classList.remove("is-dragging");
    draggedSlideId = null;
    dragSelectionIds = [];
  }

  function buildDragSelectionIds(slideId) {
    if (!slideId) {
      return [];
    }
    const selectedSet = new Set(state.selectedSlideIds || []);
    if (!selectedSet.has(slideId)) {
      return [slideId];
    }
    return state.slides.filter((slide) => selectedSet.has(slide.id)).map((slide) => slide.id);
  }

  function buildSectionThumbnailMarkup(slide) {
    const section = slide.sectionId ? findSection(slide.sectionId) : null;
    const eyebrow = slide.subsectionId ? "Subsection header" : "Section header";
    const title = section ? section.title || section.id : slide.sectionId || slide.id;
    const subsectionLabel = slide.subsectionId ? getSubsectionLabel(section, slide.subsectionId) : "";
    const subtitle = subsectionLabel
      ? `<p class="storyboard-section-thumb__subtitle">${escapeHtml(subsectionLabel)}</p>`
      : "";
    const sectionList = buildSectionThumbnailList(section, slide.subsectionId);
    return [
      '<div class="storyboard-section-thumb">',
      `<p class="storyboard-section-thumb__eyebrow">${escapeHtml(eyebrow)}</p>`,
      `<p class="storyboard-section-thumb__title">${escapeHtml(title || "Section")}</p>`,
      subtitle,
      sectionList,
      "</div>",
    ].join("");
  }

  function buildSectionThumbnailList(section, currentSubsectionId) {
    if (!section || !Array.isArray(section.subsections) || !section.subsections.length) {
      return "";
    }
    const items = section.subsections
      .map((sub) => {
        const classes = ["storyboard-section-thumb__subsection"];
        if (currentSubsectionId && sub.id === currentSubsectionId) {
          classes.push("is-current");
        }
        return `<li class="${classes.join(" ")}">${escapeHtml(sub.title || sub.id)}</li>`;
      })
      .join("");
    return `<ul class="storyboard-section-thumb__subsections">${items}</ul>`;
  }

  function getSubsectionLabel(section, subsectionId) {
    if (!section || !Array.isArray(section.subsections)) {
      return subsectionId || "";
    }
    const match = section.subsections.find((sub) => sub.id === subsectionId);
    return match ? match.title || match.id : subsectionId;
  }

  function buildStoryboardActions(slide) {
    const buttons = [];
    buttons.push(
      createStoryboardActionButton("Delete slide", "✕", (event) => {
        event.stopPropagation();
        deleteSlidesByIds([slide.id]);
      })
    );
    if (canConvertToHeaderFromStoryboard(slide)) {
      buttons.push(
        createStoryboardActionButton("Mark as section header", "↗", (event) => {
          event.stopPropagation();
          convertStoryboardSlideToHeader(slide);
        })
      );
    }
    if (!buttons.length) {
      return null;
    }
    const container = document.createElement("div");
    container.className = "slides-storyboard__actions";
    buttons.forEach((btn) => container.appendChild(btn));
    return container;
  }

  function createStoryboardActionButton(label, text, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "storyboard-action-btn";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.textContent = text;
    button.addEventListener("click", onClick);
    return button;
  }

  function canConvertToHeaderFromStoryboard(slide) {
    return Boolean(slide && slide.kind !== "sectionHeader" && state.sections.length);
  }

  function convertStoryboardSlideToHeader(slide) {
    if (!slide) {
      return;
    }
    const targetSectionId = resolveSectionForSlide(slide);
    if (!targetSectionId) {
      reportStatus("Create a section before converting a slide to a header.", true);
      return;
    }
    const section = findSection(targetSectionId);
    let subsectionId = null;
    if (section && slide.subsectionId) {
      const subsection = findSubsection(section, slide.subsectionId);
      subsectionId = subsection ? subsection.id : null;
    }
    commitSelection([slide.id], slide.id, slide.id);
    setSlideAsSectionHeader(targetSectionId, subsectionId);
  }

  function resolveSectionForSlide(slide) {
    if (!slide) {
      return null;
    }
    if (slide.sectionId && findSection(slide.sectionId)) {
      return slide.sectionId;
    }
    return state.sections.length ? state.sections[0].id : null;
  }

  function handleStoryboardZoomInput(event) {
    const value = parseFloat(event.target.value);
    if (!Number.isFinite(value)) {
      return;
    }
    applyStoryboardScale(value);
  }

  function applyStoryboardScale(scale) {
    if (!Number.isFinite(scale)) {
      return;
    }
    const clamped = Math.min(Math.max(scale, 0.6), 2);
    state.storyboardScale = clamped;
    if (elements.storyboardZoomInput && parseFloat(elements.storyboardZoomInput.value) !== clamped) {
      elements.storyboardZoomInput.value = clamped;
    }
    if (elements.storyboardGrid) {
      elements.storyboardGrid.style.setProperty("--storyboard-card-scale", clamped);
    }
  }

  function clamp(value, min, max) {
    if (!Number.isFinite(value)) {
      return min;
    }
    return Math.min(Math.max(value, min), max);
  }

  function reorderSlides(sourceIds, targetId) {
    if (!targetId) {
      return;
    }
    const ids = Array.isArray(sourceIds) ? sourceIds : [sourceIds];
    const sourceSet = new Set();
    ids.forEach((id) => {
      if (typeof id === "string" && id) {
        sourceSet.add(id);
      }
    });
    if (!sourceSet.size || sourceSet.has(targetId)) {
      return;
    }
    const slides = state.slides;
    const targetIndex = slides.findIndex((slide) => slide.id === targetId);
    if (targetIndex === -1) {
      return;
    }
    const moving = [];
    const remaining = [];
    slides.forEach((slide) => {
      if (sourceSet.has(slide.id)) {
        moving.push(slide);
      } else {
        remaining.push(slide);
      }
    });
    if (!moving.length) {
      return;
    }
    const insertIndex = remaining.findIndex((slide) => slide.id === targetId);
    if (insertIndex === -1) {
      return;
    }
    const updated = [
      ...remaining.slice(0, insertIndex),
      ...moving,
      ...remaining.slice(insertIndex),
    ];
    const changed = updated.some((slide, index) => slide !== slides[index]);
    if (!changed) {
      return;
    }
    state.slides = updated;
    state.dirty = true;
    syncDeckSummary();
    syncSectionHeaderSlides();
    renderSlideList();
    renderStoryboard();
    renderSectionsPanel();
  }

  function handleStoryboardPointerDown(event) {
    if (state.viewMode !== VIEW_MODES.STORYBOARD) {
      return;
    }
    if (!elements.storyboardGrid || event.target !== elements.storyboardGrid) {
      return;
    }
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    const marquee = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      currentX: event.clientX,
      currentY: event.clientY,
      additive: event.shiftKey || event.metaKey || event.ctrlKey,
      baseSelection: new Set(state.selectedSlideIds || []),
      currentHits: [],
    };
    state.marquee = marquee;
    showStoryboardMarquee();
    document.addEventListener("pointermove", handleStoryboardPointerMove);
    document.addEventListener("pointerup", handleStoryboardPointerUp);
    document.addEventListener("pointercancel", handleStoryboardPointerCancel);
  }

  function handleStoryboardPointerMove(event) {
    const marquee = state.marquee;
    if (!marquee || event.pointerId !== marquee.pointerId) {
      return;
    }
    event.preventDefault();
    marquee.currentX = event.clientX;
    marquee.currentY = event.clientY;
    updateStoryboardMarqueeOverlay();
  }

  function handleStoryboardPointerUp(event) {
    const marquee = state.marquee;
    if (!marquee || event.pointerId !== marquee.pointerId) {
      return;
    }
    finalizeStoryboardMarqueeSelection();
    cleanupStoryboardMarqueeListeners();
  }

  function handleStoryboardPointerCancel(event) {
    const marquee = state.marquee;
    if (!marquee || event.pointerId !== marquee.pointerId) {
      return;
    }
    clearStoryboardMarquee();
    cleanupStoryboardMarqueeListeners();
  }

  function cleanupStoryboardMarqueeListeners() {
    document.removeEventListener("pointermove", handleStoryboardPointerMove);
    document.removeEventListener("pointerup", handleStoryboardPointerUp);
    document.removeEventListener("pointercancel", handleStoryboardPointerCancel);
  }

  function showStoryboardMarquee() {
    if (elements.storyboardMarquee) {
      elements.storyboardMarquee.hidden = false;
    }
    updateStoryboardMarqueeOverlay();
  }

  function clearStoryboardMarquee() {
    state.marquee = null;
    if (elements.storyboardMarquee) {
      elements.storyboardMarquee.hidden = true;
      elements.storyboardMarquee.style.width = "0";
      elements.storyboardMarquee.style.height = "0";
    }
    applyStoryboardMarqueePreview([]);
  }

  function updateStoryboardMarqueeOverlay() {
    const marquee = state.marquee;
    if (!marquee || !elements.storyboardMarquee || !elements.storyboardGrid) {
      return;
    }
    const canvas = elements.storyboardMarquee.parentElement;
    const canvasRect = canvas ? canvas.getBoundingClientRect() : elements.storyboardGrid.getBoundingClientRect();
    const gridRect = elements.storyboardGrid.getBoundingClientRect();
    const startX = clamp(marquee.startX, canvasRect.left, canvasRect.right);
    const startY = clamp(marquee.startY, canvasRect.top, canvasRect.bottom);
    const currentX = clamp(marquee.currentX, canvasRect.left, canvasRect.right);
    const currentY = clamp(marquee.currentY, canvasRect.top, canvasRect.bottom);
    const left = Math.min(startX, currentX);
    const top = Math.min(startY, currentY);
    const width = Math.abs(currentX - startX);
    const height = Math.abs(currentY - startY);
    elements.storyboardMarquee.style.left = `${left - canvasRect.left}px`;
    elements.storyboardMarquee.style.top = `${top - canvasRect.top}px`;
    elements.storyboardMarquee.style.width = `${width}px`;
    elements.storyboardMarquee.style.height = `${height}px`;
    const region = {
      left: Math.min(startX, currentX),
      right: Math.max(startX, currentX),
      top: Math.min(startY, currentY),
      bottom: Math.max(startY, currentY),
    };
    marquee.region = region;
    const hits = collectStoryboardMarqueeHits(region);
    marquee.currentHits = hits;
    applyStoryboardMarqueePreview(hits);
  }

  function collectStoryboardMarqueeHits(region) {
    if (!elements.storyboardGrid) {
      return [];
    }
    const hits = [];
    const cards = elements.storyboardGrid.querySelectorAll(".slides-storyboard__card");
    cards.forEach((card) => {
      const rect = card.getBoundingClientRect();
      if (
        rect.right < region.left ||
        rect.left > region.right ||
        rect.bottom < region.top ||
        rect.top > region.bottom
      ) {
        return;
      }
      hits.push(card.dataset.slideId);
    });
    return hits;
  }

  function applyStoryboardMarqueePreview(hitsOverride) {
    if (!elements.storyboardGrid) {
      return;
    }
    const activeIds = new Set(hitsOverride || (state.marquee && state.marquee.currentHits) || []);
    elements.storyboardGrid.querySelectorAll(".slides-storyboard__card").forEach((card) => {
      const id = card.dataset.slideId;
      card.classList.toggle("is-marquee-preview", activeIds.has(id));
    });
  }

  function finalizeStoryboardMarqueeSelection() {
    const marquee = state.marquee;
    if (!marquee) {
      return;
    }
    const hits = marquee.currentHits || [];
    const base = marquee.additive ? new Set(marquee.baseSelection) : new Set();
    hits.forEach((id) => {
      if (id) {
        base.add(id);
      }
    });
    const selection = Array.from(base);
    if (!selection.length) {
      clearStoryboardMarquee();
      return;
    }
    const primary = selection[selection.length - 1];
    commitSelection(selection, primary, primary);
    renderSelection();
    clearStoryboardMarquee();
  }

  function handleStoryboardKeyDown(event) {
    if (state.viewMode !== VIEW_MODES.STORYBOARD) {
      return;
    }
    if (!isStoryboardNavigationKey(event)) {
      return;
    }
    if (isEditableTarget(event.target)) {
      return;
    }
    const targetId = resolveStoryboardNavigationTarget(event.key);
    if (!targetId || targetId === state.selectedSlideId) {
      return;
    }
    event.preventDefault();
    if (event.shiftKey) {
      selectSlideRange(targetId);
      return;
    }
    if (event.metaKey || event.ctrlKey) {
      toggleSlideSelection(targetId);
      return;
    }
    selectSlide(targetId);
  }

  function isStoryboardNavigationKey(event) {
    if (!event) {
      return false;
    }
    return event.key === "ArrowLeft" || event.key === "ArrowRight" || event.key === "ArrowUp" || event.key === "ArrowDown";
  }

  function resolveStoryboardNavigationTarget(direction) {
    const cards = getStoryboardCardMetadata();
    if (!cards.length) {
      return null;
    }
    let currentIndex = cards.findIndex((card) => card.id === state.selectedSlideId);
    if (currentIndex === -1) {
      return cards[0].id;
    }
    if (direction === "ArrowLeft") {
      return cards[Math.max(0, currentIndex - 1)].id;
    }
    if (direction === "ArrowRight") {
      return cards[Math.min(cards.length - 1, currentIndex + 1)].id;
    }
    if (direction === "ArrowUp") {
      return findStoryboardVerticalNeighbor(cards, currentIndex, -1);
    }
    if (direction === "ArrowDown") {
      return findStoryboardVerticalNeighbor(cards, currentIndex, 1);
    }
    return null;
  }

  function getStoryboardCardMetadata() {
    if (!elements.storyboardGrid) {
      return [];
    }
    return Array.from(elements.storyboardGrid.querySelectorAll(".slides-storyboard__card"))
      .map((card, index) => {
        const rect = card.getBoundingClientRect();
        return {
          id: card.dataset.slideId,
          index,
          rect,
          centerX: rect.left + rect.width / 2,
          centerY: rect.top + rect.height / 2,
        };
      })
      .filter((entry) => Boolean(entry.id));
  }

  function findStoryboardVerticalNeighbor(cards, currentIndex, direction) {
    const current = cards[currentIndex];
    if (!current) {
      return null;
    }
    const tolerance = 4;
    let best = null;
    let bestScore = Infinity;
    cards.forEach((card, index) => {
      if (index === currentIndex) {
        return;
      }
      const deltaY = card.centerY - current.centerY;
      if (direction < 0 ? deltaY >= -tolerance : deltaY <= tolerance) {
        return;
      }
      const dy = Math.abs(deltaY);
      const dx = Math.abs(card.centerX - current.centerX);
      const score = dy * 2 + dx;
      if (score < bestScore) {
        best = card;
        bestScore = score;
      }
    });
    if (best) {
      return best.id;
    }
    return direction < 0 ? cards[0].id : cards[cards.length - 1].id;
  }

  function isEditableTarget(target) {
    if (!target) {
      return false;
    }
    if (target.isContentEditable) {
      return true;
    }
    const editableRoot = target.closest("[contenteditable='true']");
    if (editableRoot) {
      return true;
    }
    const tag = target.tagName;
    if (!tag) {
      return false;
    }
    const blockList = ["INPUT", "TEXTAREA", "SELECT"].concat();
    return blockList.includes(tag.toUpperCase());
  }

  function selectSlide(slideId) {
    if (!slideId) {
      commitSelection([], null, null);
      renderSelection();
      return;
    }
    commitSelection([slideId], slideId, slideId);
    renderSelection();
  }

  function renderSelection() {
    const slide = getSelectedSlide();
    if (slide) {
      if (slide.kind === "sectionHeader") {
        applySectionHeaderTemplate(slide);
      }
      elements.titleInput.value = slide.titleHtml;
      elements.bodyInput.value = slide.bodyHtml;
    } else {
      elements.titleInput.value = "";
      elements.bodyInput.value = "";
    }
    renderPreview(slide || null);
    const hasSlide = Boolean(slide);
    const isHeader = Boolean(slide && slide.kind === "sectionHeader");
    elements.titleInput.disabled = !hasSlide || isHeader;
    elements.bodyInput.disabled = !hasSlide || isHeader;
    renderSlideList();
    renderStoryboard();
    const multiSelected = state.selectedSlideIds.length !== 1;
    elements.rewriteBtn.disabled = !slide || isHeader || multiSelected;
    renderSectionsPanel();
    updateSlideNavButtons();
    updateBulkActions();
    updateTagButtonState();
    refreshDirtyIndicators();
  }

  function handleSlidePointer(event, slideId) {
    if (!slideId) {
      return;
    }
    if (event && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      toggleSlideSelection(slideId);
      return;
    }
    if (event && event.shiftKey) {
      event.preventDefault();
      selectSlideRange(slideId);
      return;
    }
    selectSlide(slideId);
  }

  function selectSlideRange(targetId) {
    if (!state.slides.length) {
      return;
    }
    const anchorId = state.selectionAnchorId || state.selectedSlideId || targetId;
    const anchorIndex = state.slides.findIndex((slide) => slide.id === anchorId);
    const targetIndex = state.slides.findIndex((slide) => slide.id === targetId);
    if (anchorIndex === -1 || targetIndex === -1) {
      selectSlide(targetId);
      return;
    }
    const start = Math.min(anchorIndex, targetIndex);
    const end = Math.max(anchorIndex, targetIndex);
    const rangeIds = state.slides.slice(start, end + 1).map((slide) => slide.id);
    commitSelection(rangeIds, targetId, anchorId);
    renderSelection();
  }

  function toggleSlideSelection(slideId) {
    const selectedSet = new Set(state.selectedSlideIds || []);
    if (selectedSet.has(slideId)) {
      selectedSet.delete(slideId);
      const remaining = Array.from(selectedSet);
      const nextPrimary = remaining.length ? remaining[remaining.length - 1] : null;
      const nextAnchor = remaining.includes(state.selectionAnchorId) ? state.selectionAnchorId : nextPrimary;
      commitSelection(remaining, nextPrimary, nextAnchor);
    } else {
      selectedSet.add(slideId);
      const updated = Array.from(selectedSet);
      commitSelection(updated, slideId, slideId);
    }
    renderSelection();
  }

  function clearSlideSelection() {
    if (!state.selectedSlideIds.length) {
      return;
    }
    commitSelection([], null, null);
    renderSelection();
  }

  function bulkPromoteSelectedSlides() {
    const ids = state.selectedSlideIds || [];
    if (!ids.length) {
      reportStatus("Select at least one slide to promote.");
      return;
    }
    const selectionSet = new Set(ids);
    const firstIndex = getFirstSelectedIndex(selectionSet);
    if (firstIndex <= 0) {
      reportStatus("Selected slides are already at the top of the deck.");
      return;
    }
    const selectedSlides = state.slides.filter((slide) => selectionSet.has(slide.id));
    if (!selectedSlides.length) {
      return;
    }
    const previousSlide = state.slides[firstIndex - 1] || null;
    const remainingSlides = state.slides.filter((slide) => !selectionSet.has(slide.id));
    let insertIndex = 0;
    if (previousSlide) {
      insertIndex = remainingSlides.findIndex((slide) => slide.id === previousSlide.id);
      if (insertIndex === -1) {
        insertIndex = 0;
      }
    }
    remainingSlides.splice(insertIndex, 0, ...selectedSlides);
    state.slides = remainingSlides;
    state.dirty = true;
    syncDeckSummary();
    syncSectionHeaderSlides();
    renderSlideList();
    renderSectionsPanel();
    reportStatus("Promoted selected slides.");
  }

  function bulkDemoteSelectedSlides() {
    const ids = state.selectedSlideIds || [];
    if (!ids.length) {
      reportStatus("Select at least one slide to demote.");
      return;
    }
    const selectionSet = new Set(ids);
    const lastIndex = getLastSelectedIndex(selectionSet);
    if (lastIndex === -1 || lastIndex >= state.slides.length - 1) {
      reportStatus("Selected slides are already at the end of the deck.");
      return;
    }
    const selectedSlides = state.slides.filter((slide) => selectionSet.has(slide.id));
    if (!selectedSlides.length) {
      return;
    }
    const nextSlide = state.slides[lastIndex + 1] || null;
    const remainingSlides = state.slides.filter((slide) => !selectionSet.has(slide.id));
    let insertIndex = remainingSlides.length;
    if (nextSlide) {
      const nextIndex = remainingSlides.findIndex((slide) => slide.id === nextSlide.id);
      if (nextIndex !== -1) {
        insertIndex = nextIndex + 1;
      }
    }
    remainingSlides.splice(insertIndex, 0, ...selectedSlides);
    state.slides = remainingSlides;
    state.dirty = true;
    syncDeckSummary();
    syncSectionHeaderSlides();
    renderSlideList();
    renderSectionsPanel();
    reportStatus("Demoted selected slides.");
  }

  function getFirstSelectedIndex(selectionSet) {
    if (!state.slides.length || !state.selectedSlideIds.length) {
      return -1;
    }
    const targetSet = selectionSet || new Set(state.selectedSlideIds);
    return state.slides.findIndex((slide) => targetSet.has(slide.id));
  }

  function getLastSelectedIndex(selectionSet) {
    if (!state.slides.length || !state.selectedSlideIds.length) {
      return -1;
    }
    const targetSet = selectionSet || new Set(state.selectedSlideIds);
    for (let idx = state.slides.length - 1; idx >= 0; idx -= 1) {
      if (targetSet.has(state.slides[idx].id)) {
        return idx;
      }
    }
    return -1;
  }

  function commitSelection(nextIds, primaryId, anchorId) {
    const validIds = new Set(state.slides.map((slide) => slide.id));
    const uniqueIds = [];
    const seen = new Set();
    (nextIds || []).forEach((id) => {
      if (!validIds.has(id) || seen.has(id)) {
        return;
      }
      seen.add(id);
      uniqueIds.push(id);
    });
    let resolvedPrimary = primaryId && validIds.has(primaryId) ? primaryId : null;
    if (!resolvedPrimary && uniqueIds.length) {
      resolvedPrimary = uniqueIds[uniqueIds.length - 1];
    }
    let resolvedAnchor = anchorId && validIds.has(anchorId) ? anchorId : resolvedPrimary;
    state.selectedSlideIds = uniqueIds;
    state.selectedSlideId = resolvedPrimary;
    state.selectionAnchorId = resolvedAnchor || null;
  }

  function ensureSelectionIntegrity(preferredId = null) {
    const validIds = new Set(state.slides.map((slide) => slide.id));
    const preserved = (state.selectedSlideIds || []).filter((id) => validIds.has(id));
    if (preferredId && validIds.has(preferredId) && !preserved.includes(preferredId)) {
      preserved.push(preferredId);
    }
    let primary = state.selectedSlideId && validIds.has(state.selectedSlideId) ? state.selectedSlideId : null;
    if (!primary) {
      primary = preferredId && validIds.has(preferredId) ? preferredId : preserved[preserved.length - 1] || null;
    }
    if (!primary && preserved.length === 0 && state.slides.length) {
      primary = state.slides[0].id;
      preserved.push(primary);
    }
    const anchor = state.selectionAnchorId && validIds.has(state.selectionAnchorId) ? state.selectionAnchorId : primary;
    commitSelection(preserved, primary, anchor);
  }

  function updateBulkActions() {
    const count = state.selectedSlideIds.length;
    updateSelectionControls(
      {
        container: elements.bulkActionsBar,
        summary: elements.bulkSelectionSummary,
        deleteBtn: elements.bulkDeleteBtn,
        promoteBtn: elements.bulkPromoteBtn,
        demoteBtn: elements.bulkDemoteBtn,
        clearBtn: elements.bulkClearSelectionBtn,
      },
      count
    );
    updateSelectionControls(
      {
        container: elements.storyboardSelectionBanner,
        summary: elements.storyboardSelectionSummary,
        deleteBtn: elements.storyboardDeleteBtn,
        promoteBtn: elements.storyboardPromoteBtn,
        demoteBtn: elements.storyboardDemoteBtn,
        clearBtn: elements.storyboardClearBtn,
      },
      count
    );
  }

  function updateSelectionControls(config, count) {
    if (!config || !config.summary || !config.container) {
      return;
    }
    const emptyLabel = config.summary.dataset.emptyLabel || "No slides selected";
    const singleLabel = config.summary.dataset.singleLabel || "1 slide selected";
    const multiLabelTemplate = config.summary.dataset.multiLabel || "{count} slides selected";
    if (!count) {
      config.summary.textContent = emptyLabel;
      config.container.hidden = true;
    } else {
      const label =
        count === 1 ? singleLabel : multiLabelTemplate.replace("{count}", count.toString());
      config.summary.textContent = label;
      config.container.hidden = false;
    }
    const disable = count === 0;
    if (config.deleteBtn) {
      config.deleteBtn.disabled = disable;
    }
    if (config.clearBtn) {
      config.clearBtn.disabled = disable;
    }
    if (config.promoteBtn) {
      const topLocked = disable || getFirstSelectedIndex() <= 0;
      config.promoteBtn.disabled = topLocked;
    }
    if (config.demoteBtn) {
      const bottomLocked = disable || getLastSelectedIndex() === state.slides.length - 1;
      config.demoteBtn.disabled = bottomLocked;
    }
  }

  function refreshDirtyIndicators() {
    if (!elements.storyboardDirtyBanner) {
      return;
    }
    const dirty = Boolean(state.dirty);
    elements.storyboardDirtyBanner.hidden = !dirty;
    if (elements.storyboardSaveBtn) {
      elements.storyboardSaveBtn.disabled = !dirty || !state.currentDeckId;
    }
  }

  function getSelectedSlide() {
    return state.slides.find((item) => item.id === state.selectedSlideId) || null;
  }

  function updateSlideNavButtons() {
    if (!elements.prevSlideBtn && !elements.nextSlideBtn) {
      return;
    }
    const total = state.slides.length;
    const currentIndex = state.slides.findIndex((slide) => slide.id === state.selectedSlideId);
    const hasSelection = currentIndex !== -1;
    if (elements.prevSlideBtn) {
      const disabled = !total || !hasSelection || currentIndex <= 0;
      elements.prevSlideBtn.disabled = disabled;
    }
    if (elements.nextSlideBtn) {
      const disabled = !total || !hasSelection || currentIndex >= total - 1;
      elements.nextSlideBtn.disabled = disabled;
    }
  }

  function selectAdjacentSlide(offset) {
    if (!state.slides.length) {
      return;
    }
    let index = state.slides.findIndex((slide) => slide.id === state.selectedSlideId);
    if (index === -1) {
      index = offset > 0 ? -1 : state.slides.length;
    }
    const targetIndex = index + offset;
    if (targetIndex < 0 || targetIndex >= state.slides.length) {
      return;
    }
    const target = state.slides[targetIndex];
    if (target) {
      selectSlide(target.id);
    }
  }

  function setViewMode(mode) {
    if (!elements.storyboardGrid || state.viewMode === mode) {
      state.viewMode = mode;
      updateViewToggle();
      return;
    }
    state.viewMode = mode;
    updateViewToggle();
    renderStoryboard();
  }

  function updateViewToggle() {
    if (!elements.storyboardGrid || !elements.slideList) {
      return;
    }
    const isStoryboard = state.viewMode === VIEW_MODES.STORYBOARD;
    if (elements.storyboardPane) {
      elements.storyboardPane.hidden = !isStoryboard;
    }
    if (elements.workspaceDetailPane) {
      elements.workspaceDetailPane.hidden = isStoryboard;
    }
    elements.storyboardGrid.hidden = !isStoryboard;
    elements.slideList.hidden = isStoryboard;
    if (elements.viewStoryboardBtn) {
      elements.viewStoryboardBtn.classList.toggle("is-active", isStoryboard);
      elements.viewStoryboardBtn.disabled = isStoryboard;
    }
    if (elements.viewListBtn) {
      elements.viewListBtn.classList.toggle("is-active", !isStoryboard);
      elements.viewListBtn.disabled = !isStoryboard;
    }
    applyStoryboardScale(state.storyboardScale || 1);
  }

  function renderStoryboard() {
    if (!elements.storyboardGrid) {
      return;
    }
    if (state.viewMode !== VIEW_MODES.STORYBOARD) {
      elements.storyboardGrid.innerHTML = "";
      return;
    }
    applyStoryboardScale(state.storyboardScale || 1);
    const fragment = document.createDocumentFragment();
    const selectedSet = new Set(state.selectedSlideIds || []);
    state.slides.forEach((slide, index) => {
      const card = document.createElement("div");
      card.className = "slides-storyboard__card";
      const isSelected = selectedSet.has(slide.id);
      const isPrimary = slide.id === state.selectedSlideId;
      if (isSelected) {
        card.classList.add("is-selected");
      }
      if (isPrimary) {
        card.classList.add("is-active");
      }
      card.dataset.slideId = slide.id;
      card.draggable = true;
      card.addEventListener("dragstart", handleStoryboardDragStart);
      card.addEventListener("dragover", handleStoryboardDragOver);
      card.addEventListener("drop", handleStoryboardDrop);
      card.addEventListener("dragend", handleStoryboardDragEnd);

      card.title = getSlideLabel(slide);
      const thumb = document.createElement("div");
      thumb.className = "slides-storyboard__thumb";
      const thumbnailHtml = (state.thumbnails && state.thumbnails[slide.id]) || "";
      if (slide.kind === "sectionHeader") {
        thumb.innerHTML = buildSectionThumbnailMarkup(slide);
      } else if (thumbnailHtml) {
        thumb.innerHTML = thumbnailHtml;
      } else {
        const placeholder = "(empty slide)";
        thumb.innerHTML = `<span class="preview-placeholder">${escapeHtml(placeholder)}</span>`;
      }
      const badge = document.createElement("span");
      badge.className = "slides-storyboard__badge";
      badge.textContent = index + 1;

      const actions = buildStoryboardActions(slide);

      card.appendChild(thumb);
      card.appendChild(badge);
      if (actions) {
        card.appendChild(actions);
      }
      card.addEventListener("click", (event) => handleSlidePointer(event, slide.id));
      fragment.appendChild(card);
    });
    elements.storyboardGrid.replaceChildren(fragment);
    applyStoryboardMarqueePreview();
  }

  function canPromoteSelectedSlide() {
    const slide = getSelectedSlide();
    return Boolean(slide && slide.kind !== "sectionHeader");
  }

  function renderPreview(slide) {
    if (!elements.previewFrame || !elements.previewFallback || !elements.previewTitle || !elements.previewBody) {
      return;
    }
    if (!slide) {
      elements.previewFrame.hidden = true;
      elements.previewFrame.srcdoc = "";
      elements.previewFallback.hidden = false;
      elements.previewTitle.textContent = "No slide selected";
      elements.previewBody.innerHTML = "Choose a slide from the list to see its preview.";
      return;
    }
    if (slide.kind === "sectionHeader") {
      const preview = computeSectionHeaderContent(slide.sectionId, slide.subsectionId);
      elements.previewFrame.hidden = true;
      elements.previewFrame.srcdoc = "";
      elements.previewFallback.hidden = false;
      elements.previewTitle.innerHTML = preview.titleHtml || "(Section header)";
      elements.previewBody.innerHTML = preview.bodyHtml || "";
      return;
    }
    elements.previewFallback.hidden = true;
    elements.previewFrame.hidden = false;
    elements.previewFrame.setAttribute(
      "title",
      `Preview of ${stripHtml(slide.titleHtml) || slide.id || "current slide"}`
    );
    elements.previewFrame.style.height = "";
    elements.previewFrame.style.width = "";
    elements.previewFrame.srcdoc = buildSlidePreviewDocument(slide);
    elements.previewFrame.addEventListener("load", handlePreviewFrameLoad, { once: true });
  }

  function handlePreviewFrameLoad(event) {
    const frame = event?.currentTarget;
    if (!frame || frame.hidden) {
      return;
    }
    const doc = frame.contentWindow && frame.contentWindow.document;
    if (!doc) {
      return;
    }
    const measurements = measurePreviewDocument(doc);
    const parentWidth = getPreviewContainerWidth(frame);
    const measurementWidth = measurements.contentWidth || measurements.width;
    const scale = applyPreviewScale(doc, measurementWidth, parentWidth);
    const baseHeight = measurements.contentHeight || measurements.height;
    const scaledHeight = baseHeight ? Math.ceil(baseHeight * scale) : 0;
    if (scaledHeight) {
      frame.style.height = `${scaledHeight}px`;
    }
    const scaledWidth = measurementWidth ? Math.ceil(measurementWidth * scale) : 0;
    const targetWidth = parentWidth || scaledWidth || measurements.width;
    if (targetWidth) {
      frame.style.width = `${targetWidth}px`;
    }
  }

  function getPreviewContainerWidth(frame) {
    if (!frame) {
      return 0;
    }
    const parent = frame.parentElement;
    if (!parent) {
      return 0;
    }
    if (parent.clientWidth) {
      return parent.clientWidth;
    }
    const rect = typeof parent.getBoundingClientRect === "function" ? parent.getBoundingClientRect() : null;
    return rect ? rect.width : 0;
  }

  function measurePreviewDocument(doc) {
    const root = doc.documentElement;
    const body = doc.body;
    const rootBox = measureNodeBox(root);
    const bodyBox = measureNodeBox(body);
    const contentBox = measureContentBounds(body);
    const slideContainer = body ? body.querySelector(".slide-container") : null;
    const slideBox = measureNodeBox(slideContainer);
    const preferredWidth = slideBox.width || contentBox.width || bodyBox.width || rootBox.width;
    const preferredHeight = slideBox.height || contentBox.height || bodyBox.height || rootBox.height;
    return {
      height: Math.max(rootBox.height, bodyBox.height, contentBox.height, slideBox.height),
      width: Math.max(rootBox.width, bodyBox.width, contentBox.width, slideBox.width),
      contentWidth: preferredWidth,
      contentHeight: preferredHeight,
    };
  }

  function measureNodeBox(node) {
    if (!node) {
      return { width: 0, height: 0 };
    }
    const rect = typeof node.getBoundingClientRect === "function" ? node.getBoundingClientRect() : null;
    const width = Math.max(
      rect ? rect.width : 0,
      typeof node.scrollWidth === "number" ? node.scrollWidth : 0,
      typeof node.clientWidth === "number" ? node.clientWidth : 0
    );
    const height = Math.max(
      rect ? rect.height : 0,
      typeof node.scrollHeight === "number" ? node.scrollHeight : 0,
      typeof node.clientHeight === "number" ? node.clientHeight : 0
    );
    return { width, height };
  }

  function measureContentBounds(container) {
    if (!container || typeof container.getElementsByTagName !== "function") {
      return { width: 0, height: 0 };
    }
    const nodes = container.getElementsByTagName("*");
    const limit = Math.min(nodes.length, PREVIEW_CONTENT_MEASUREMENT_LIMIT);
    if (!limit) {
      return { width: 0, height: 0 };
    }
    let width = 0;
    let height = 0;
    for (let index = 0; index < limit; index += 1) {
      const element = nodes[index];
      if (!element || typeof element.getBoundingClientRect !== "function") {
        continue;
      }
      const rect = element.getBoundingClientRect();
      const elementWidth = Math.max(
        rect ? rect.width : 0,
        typeof element.scrollWidth === "number" ? element.scrollWidth : 0,
        typeof element.clientWidth === "number" ? element.clientWidth : 0
      );
      const elementHeight = Math.max(
        rect ? rect.height : 0,
        typeof element.scrollHeight === "number" ? element.scrollHeight : 0,
        typeof element.clientHeight === "number" ? element.clientHeight : 0
      );
      width = Math.max(width, elementWidth);
      height = Math.max(height, elementHeight);
    }
    return { width, height };
  }

  function applyPreviewScale(doc, documentWidth, parentWidth) {
    if (!doc) {
      return 1;
    }
    resetPreviewScale(doc);
    const desiredScale = calculatePreviewScale(documentWidth, parentWidth);
    if (desiredScale === 1) {
      return 1;
    }
    const root = doc.documentElement;
    const body = doc.body;
    if (tryApplyZoom(root, body, desiredScale)) {
      return desiredScale;
    }
    applyTransformScale(root, body, desiredScale);
    return desiredScale;
  }

  function calculatePreviewScale(documentWidth, parentWidth) {
    if (!documentWidth || !parentWidth) {
      return 1;
    }
    const ratio = parentWidth / documentWidth;
    if (!Number.isFinite(ratio) || Math.abs(ratio - 1) < PREVIEW_SCALE_EPSILON) {
      return 1;
    }
    return Math.min(Math.max(ratio, MIN_PREVIEW_SCALE), MAX_PREVIEW_SCALE);
  }

  function resetPreviewScale(doc) {
    const targets = [doc && doc.documentElement, doc && doc.body];
    targets.forEach((node) => {
      if (!node || !node.style) {
        return;
      }
      node.style.removeProperty("zoom");
      node.style.removeProperty("transform");
      node.style.removeProperty("transform-origin");
    });
  }

  function tryApplyZoom(root, body, scale) {
    if (!root || !root.style || typeof root.style.zoom === "undefined") {
      return false;
    }
    root.style.zoom = scale;
    if (body && body.style) {
      body.style.zoom = scale;
    }
    const view = root.ownerDocument ? root.ownerDocument.defaultView : null;
    if (!view || typeof view.getComputedStyle !== "function") {
      return true;
    }
    const computed = view.getComputedStyle(root).getPropertyValue("zoom");
    if (!computed || computed === "normal") {
      root.style.removeProperty("zoom");
      if (body && body.style) {
        body.style.removeProperty("zoom");
      }
      return false;
    }
    return true;
  }

  function applyTransformScale(root, body, scale) {
    const targets = [root, body];
    targets.forEach((node) => {
      if (!node || !node.style) {
        return;
      }
      node.style.transformOrigin = "top left";
      node.style.transform = `scale(${scale})`;
    });
  }

  function updateCurrentSlide(field, value) {
    const slide = state.slides.find((item) => item.id === state.selectedSlideId);
    if (!slide || slide.kind === "sectionHeader") {
      return;
    }
    if (field === "titleHtml") {
      slide.titleHtml = value;
    } else {
      slide.bodyHtml = value;
    }
    state.dirty = true;
    renderPreview(slide);
    syncDeckSummary();
    renderSlideList();
  }

  function addSlideAfterCurrent() {
    const newSlideId = nextSlideId();
    const newSlide = {
      id: newSlideId,
      titleHtml: "",
      bodyHtml: "",
      notesHtml: "",
      sourceHtml: "",
      fullHtml: "",
      kind: "normal",
      sectionId: null,
      subsectionId: null,
    };
    if (!state.slides.length) {
      state.slides.push(newSlide);
    } else {
      const index = state.slides.findIndex((slide) => slide.id === state.selectedSlideId);
      if (index === -1) {
        state.slides.push(newSlide);
      } else {
        state.slides.splice(index + 1, 0, newSlide);
      }
    }
    commitSelection([newSlideId], newSlideId, newSlideId);
    state.dirty = true;
    syncDeckSummary();
    renderSlideList();
    renderSelection();
    renderSectionsPanel();
  }

  function deleteCurrentSlide() {
    deleteSlidesByIds(state.selectedSlideIds || []);
  }

  function deleteSlidesByIds(ids) {
    const unique = Array.from(new Set(ids || [])).filter(Boolean);
    if (!unique.length) {
      return;
    }
    const removals = unique
      .map((id) => ({ id, index: state.slides.findIndex((slide) => slide.id === id) }))
      .filter((entry) => entry.index !== -1);
    if (!removals.length) {
      return;
    }
    const descending = [...removals].sort((a, b) => b.index - a.index);
    const ascending = [...removals].sort((a, b) => a.index - b.index);
    descending.forEach(({ index }) => {
      const [removed] = state.slides.splice(index, 1);
      handleSlideRemoval(removed, index);
    });
    if (state.slides.length) {
      const fallbackIndex = Math.min(ascending[0].index, state.slides.length - 1);
      const fallbackId = state.slides[fallbackIndex] ? state.slides[fallbackIndex].id : state.slides[0].id;
      commitSelection([fallbackId], fallbackId, fallbackId);
    } else {
      commitSelection([], null, null);
    }
    state.dirty = true;
    syncDeckSummary();
    renderSlideList();
    renderSelection();
    renderSectionsPanel();
  }

  function nextSlideId() {
    const pattern = /^slide(\d+)\.html$/i;
    let max = -1;
    state.slides.forEach((slide) => {
      const match = pattern.exec(slide.id);
      if (match) {
        const value = parseInt(match[1], 10);
        if (!Number.isNaN(value)) {
          max = Math.max(max, value);
        }
      }
    });
    return `slide${max + 1}.html`;
  }

  function saveDeck() {
    if (!state.currentDeckId) {
      reportStatus("Select a deck before saving.", true);
      return;
    }
    syncSectionHeaderSlides();
    reportStatus("Saving deck… semantic OCR may run via LLM, so this can take a moment.");
    const payload = {
      slides: state.slides.map((slide) => ({
        id: slide.id,
        titleHtml: slide.titleHtml,
        bodyHtml: slide.bodyHtml,
        notesHtml: slide.notesHtml,
        sourceHtml: slide.sourceHtml,
        fullHtml: slide.fullHtml,
        kind: slide.kind,
        sectionId: slide.sectionId,
        subsectionId: slide.subsectionId,
      })),
      sections: cloneSections(state.sections),
    };
    elements.saveBtn.disabled = true;
    fetchJson(`/slides/deck/${encodeURIComponent(state.currentDeckId)}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(() => {
        state.dirty = false;
        updateDeckSummary({ deckId: state.currentDeckId, slides: state.slides });
        reportStatus("Deck saved successfully.");
        refreshDirtyIndicators();
      })
      .catch((error) => {
        reportStatus(`Failed to save deck: ${error.message}`, true);
      })
      .finally(() => {
        elements.saveBtn.disabled = false;
      });
  }

  function rewriteCurrentSlide() {
    if (!state.currentDeckId || !state.selectedSlideId) {
      return;
    }
    const slide = state.slides.find((item) => item.id === state.selectedSlideId);
    if (!slide || slide.kind === "sectionHeader") {
      return;
    }
    elements.rewriteBtn.disabled = true;
    const payload = {
      slideId: slide.id,
      titleHtml: slide.titleHtml,
      bodyHtml: slide.bodyHtml,
    };
    fetchJson(`/slides/deck/${encodeURIComponent(state.currentDeckId)}/rewrite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((response) => {
        slide.titleHtml = response.titleHtml;
        slide.bodyHtml = response.bodyHtml;
        if (Object.prototype.hasOwnProperty.call(response, "notesHtml")) {
          slide.notesHtml = response.notesHtml;
        }
        if (Object.prototype.hasOwnProperty.call(response, "sourceHtml")) {
          slide.sourceHtml = response.sourceHtml;
        }
        if (Object.prototype.hasOwnProperty.call(response, "fullHtml")) {
          slide.fullHtml = response.fullHtml;
        }
        state.dirty = true;
        renderSelection();
        syncDeckSummary();
        reportStatus("Slide rewritten.");
      })
      .catch((error) => {
        reportStatus(`Rewrite failed: ${error.message}`, true);
      })
      .finally(() => {
        elements.rewriteBtn.disabled = false;
      });
  }

  function tagSlides() {
    if (!state.currentDeckId || state.tagging) {
      return;
    }
    // Only multi-select scopes tagging; a single auto-selected slide should not limit tagging.
    const hasSelection = state.selectedSlideIds && state.selectedSlideIds.length > 1;
    const targetIds = hasSelection ? [...new Set(state.selectedSlideIds)] : [];
    if (!hasSelection && (!state.slides || !state.slides.length)) {
      reportStatus("No slides selected to tag.", true);
      return;
    }
    state.tagging = true;
    updateTagButtonState();
    const taggingScope = hasSelection
      ? `${targetIds.length} selected`
      : `${state.slides.length} total (untagged only)`;
    reportStatus(`Tagging ${taggingScope} slide(s)...`);
    // Default path retags the full deck; selection scopes to those slides.
    const payload = hasSelection
      ? { slideIds: targetIds, mode: "full" }
      : { mode: "full" };
    fetchJson(`/slides/deck/${encodeURIComponent(state.currentDeckId)}/tag`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((result) => {
        if (result && result.status === "succeeded" && !result.jobId) {
          const tagged = Array.isArray(result.taggedSlides) ? result.taggedSlides.length : 0;
          const skipped = Array.isArray(result.skippedSlides) ? result.skippedSlides.length : 0;
          renderTagSummary({
            tagged,
            skipped,
            metricClusters: 0,
            recoClusters: 0,
            unlinked: 0,
            metricDuplicates: {},
            recommendationDuplicates: {},
            missingRecommendationLinks: [],
            issueCount: 0,
          });
          reportStatus(result.message || "Nothing to tag (already up to date).");
          state.tagging = false;
          updateTagButtonState();
          return;
        }
        if (!result || !result.jobId) {
          throw new Error("Tagging job did not return an identifier.");
        }
        setCurrentTagJob(result.jobId);
        const email = result.notifyEmail || "your account email";
        reportStatus(`Tagging submitted. We'll email ${email} when it's finished.`);
        pollTagJob(result.jobId, 0);
      })
      .catch((error) => {
        reportStatus(`Tagging failed: ${error.message}`, true);
        renderTagSummary(null);
        state.tagging = false;
        updateTagButtonState();
      });
  }

  function pollTagJob(jobId, attempt) {
    fetchJson(`/slides/deck/tag/${jobId}`)
      .then((status) => {
        const statusValue = status.status;
        const totalSlides = typeof status.totalSlides === "number" ? status.totalSlides : null;
        if (statusValue === "pending" || statusValue === "running") {
          const delay = Math.min(30000, 1000 + attempt * 250);
          setTimeout(() => pollTagJob(jobId, attempt + 1), delay);
          return;
        }
        if (statusValue === "succeeded") {
          const tagged = Array.isArray(status.taggedSlides) ? status.taggedSlides.length : 0;
          const skipped = Array.isArray(status.skippedSlides) ? status.skippedSlides.length : 0;
          const metricClusters = status.metricDuplicates ? Object.keys(status.metricDuplicates).length : 0;
          const recoClusters = status.recommendationDuplicates
            ? Object.keys(status.recommendationDuplicates).length
            : 0;
          const unlinked = Array.isArray(status.missingRecommendationLinks)
            ? status.missingRecommendationLinks.length
            : 0;
          const detailIssues = Array.isArray(status.details)
            ? status.details.filter(
                (item) =>
                  item.issues &&
                  item.issues.length &&
                  !(
                    item.issues.length === 1 &&
                    item.issues[0] === "LLM returned no enrichment; kept stamped tags"
                  )
              ).length
            : 0;
          reportStatus(
            `Tagged ${tagged} slide(s); skipped ${skipped}; metric dup clusters ${metricClusters}; recommendation dup clusters ${recoClusters}; unlinked recos ${unlinked}.`
          );
          renderTagSummary({
            tagged,
            skipped,
            metricClusters,
            recoClusters,
            unlinked,
            metricDuplicates: status.metricDuplicates || {},
            recommendationDuplicates: status.recommendationDuplicates || {},
            missingRecommendationLinks: status.missingRecommendationLinks || [],
            issueCount: detailIssues,
          });
          state.tagging = false;
          clearCurrentTagJob();
          updateTagButtonState();
          return loadDeck(state.currentDeckId);
        }
        if (statusValue === "failed") {
          const reason = status.detail ? `: ${status.detail}` : "";
          reportStatus(`Tagging failed${reason}`, true);
          renderTagSummary(null);
          state.tagging = false;
          clearCurrentTagJob();
          updateTagButtonState();
          return;
        }
      })
      .catch((error) => {
        reportStatus(`Tagging failed: ${error.message}`, true);
        renderTagSummary(null);
        state.tagging = false;
        clearCurrentTagJob();
        updateTagButtonState();
      });
  }

  function openImportDialog() {
    if (!state.currentDeckId) {
      return;
    }
    state.importing = true;
    elements.importDialog.classList.remove("hidden");
    elements.importSlideList.innerHTML = "";
    renderImportDeckOptions();
    renderImportSlides();
  }

  function closeImportDialog() {
    state.importing = false;
    elements.importDialog.classList.add("hidden");
  }

  function openConcatDialog() {
    if (!elements.concatDialog) {
      return;
    }
    if (!state.decks.length) {
      reportStatus("Upload or load at least one deck before combining.", true);
      return;
    }
    if (elements.concatDeckNameInput) {
      elements.concatDeckNameInput.value = suggestConcatDeckId();
    }
    renderConcatDeckOptions();
    elements.concatDialog.classList.remove("hidden");
  }

  function closeConcatDialog() {
    if (!elements.concatDialog) {
      return;
    }
    elements.concatDialog.classList.add("hidden");
    if (elements.concatDeckList) {
      elements.concatDeckList.innerHTML = "";
    }
  }

  function renderConcatDeckOptions() {
    if (!elements.concatDeckList) {
      return;
    }
    elements.concatDeckList.innerHTML = "";
    state.decks.forEach((deck) => {
      const item = document.createElement("label");
      item.className = "slides-import__item slides-import__checkbox";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = deck.deckId;
      if (deck.deckId === state.currentDeckId) {
        checkbox.checked = true;
      }
      const name = document.createElement("span");
      name.textContent = deck.deckId;
      item.appendChild(checkbox);
      item.appendChild(name);
      elements.concatDeckList.appendChild(item);
    });
  }

  function handleConcatConfirm() {
    if (state.concatenating) {
      return;
    }
    const nameInput = elements.concatDeckNameInput;
    if (!nameInput || !elements.concatDeckList) {
      return;
    }
    const deckId = nameInput.value.trim();
    if (!deckId) {
      reportStatus("Provide a name for the combined deck.", true);
      return;
    }
    const selected = getSelectedConcatDecks();
    if (!selected.length) {
      reportStatus("Select at least one deck to combine.", true);
      return;
    }
    state.concatenating = true;
    if (elements.concatConfirmBtn) {
      elements.concatConfirmBtn.disabled = true;
    }
    fetchJson("/slides/deck/concatenate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ newDeckId: deckId, sourceDeckIds: selected }),
    })
      .then((deck) => {
        applyDeckResponse(deck);
        closeConcatDialog();
        reportStatus(`Created deck ${deck.deckId}.`);
      })
      .catch((error) => {
        reportStatus(`Failed to combine decks: ${error.message}`, true);
      })
      .finally(() => {
        state.concatenating = false;
        if (elements.concatConfirmBtn) {
          elements.concatConfirmBtn.disabled = false;
        }
      });
  }

  function getSelectedConcatDecks() {
    if (!elements.concatDeckList) {
      return [];
    }
    return Array.from(
      elements.concatDeckList.querySelectorAll('input[type="checkbox"]:checked')
    ).map((input) => input.value);
  }

  function suggestConcatDeckId() {
    if (state.currentDeckId) {
      return `${state.currentDeckId}-combined`;
    }
    return `deck-${Date.now()}`;
  }

  function handlePrintDeck() {
    if (!state.currentDeckId) {
      reportStatus("Load a deck before printing.", true);
      return;
    }
    if (state.printing) {
      reportStatus("PDF export already in progress.");
      return;
    }
    setPrinting(true);
    reportStatus(`Generating PDF for ${state.currentDeckId}…`);
    fetchJson(`/slides/deck/${encodeURIComponent(state.currentDeckId)}/print`, {
      method: "POST",
    })
      .then((data) => {
        if (!data || !data.jobId) {
          throw new Error("PDF job did not return an identifier.");
        }
        reportStatus(`PDF export started… (job ${data.jobId})`);
        pollPrintJobStatus(data.jobId, 0);
      })
      .catch((error) => {
        reportStatus(`PDF export failed: ${error.message}`, true);
        setPrinting(false);
      });
  }

  function pollPrintJobStatus(jobId, attempt) {
    fetchJson(`/slides/deck/print/${jobId}`)
      .then((status) => {
        const statusValue = status.status;
        if (statusValue === "succeeded" && status.downloadUrl) {
          downloadPrintJob(status.downloadUrl);
        } else if (statusValue === "failed") {
          const reason = status.detail ? `: ${status.detail}` : "";
          reportStatus(`PDF export failed${reason}`, true);
          setPrinting(false);
        } else {
          const delay = Math.min(5000, 1000 + attempt * 250);
          schedulePrintPoll(jobId, delay, attempt + 1);
        }
      })
      .catch((error) => {
        reportStatus(`PDF export failed: ${error.message}`, true);
        setPrinting(false);
      });
  }

  function schedulePrintPoll(jobId, delay, nextAttempt) {
    if (state.printJobTimer) {
      clearTimeout(state.printJobTimer);
    }
    state.printJobTimer = setTimeout(() => {
      pollPrintJobStatus(jobId, nextAttempt);
    }, delay);
  }

  function downloadPrintJob(downloadUrl) {
    fetch(downloadUrl)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to download PDF.");
        }
        return response.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${state.currentDeckId || "deck"}.pdf`;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
        reportStatus(`Downloaded ${state.currentDeckId || "deck"}.pdf.`);
      })
      .catch((error) => {
        reportStatus(`PDF export failed: ${error.message}`, true);
      })
      .finally(() => {
        setPrinting(false);
      });
  }

  function renderImportDeckOptions() {
    elements.importDeckSelect.innerHTML = "";
    state.decks.forEach((deck) => {
      const option = document.createElement("option");
      option.value = deck.deckId;
      option.textContent = deck.deckId;
      elements.importDeckSelect.appendChild(option);
    });
    if (state.currentDeckId) {
      elements.importDeckSelect.value = state.decks.find((deck) => deck.deckId !== state.currentDeckId)?.deckId || state.currentDeckId;
    }
  }

  function renderImportSlides() {
    const deckId = elements.importDeckSelect.value || state.currentDeckId;
    const deck = state.decks.find((item) => item.deckId === deckId);
    elements.importSlideList.innerHTML = "";
    if (!deck || !deck.slides) {
      return;
    }
    deck.slides.forEach((slide) => {
      const normalized = normalizeSlide(slide);
      const item = document.createElement("li");
      item.className = "slides-import__item";
      item.tabIndex = 0;
      const label = stripHtml(normalized.titleHtml) || normalized.id;
      item.textContent =
        normalized.kind === "sectionHeader" ? `Header · ${label}` : label;
      item.addEventListener("click", () => confirmImport(deck.deckId, normalized.id));
      item.addEventListener("keypress", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          confirmImport(deck.deckId, normalized.id);
        }
      });
      elements.importSlideList.appendChild(item);
    });
  }

  function confirmImport(sourceDeckId, sourceSlideId) {
    if (!state.currentDeckId) {
      return;
    }
    const payload = {
      sourceDeckId,
      sourceSlideId,
      afterSlideId: state.selectedSlideId,
      currentOrder: state.slides.map((slide) => slide.id),
    };
    fetchJson(`/slides/deck/${encodeURIComponent(state.currentDeckId)}/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((response) => {
        const slide = normalizeSlide(response.slide);
        const order = response.order || [];
        const existing = new Map(state.slides.map((item) => [item.id, item]));
        existing.set(slide.id, slide);
        state.slides = order.map((id) => existing.get(id)).filter(Boolean);
        commitSelection([slide.id], slide.id, slide.id);
        state.dirty = true;
        renderSlideList();
        renderSelection();
        closeImportDialog();
        syncDeckSummary();
        syncSectionHeaderSlides();
        renderSectionsPanel();
        reportStatus(`Imported ${slide.id} from ${sourceDeckId}.`);
      })
      .catch((error) => {
        reportStatus(`Import failed: ${error.message}`, true);
      });
  }

  function triggerDeckUpload() {
    if (state.uploading) {
      reportStatus("Please wait for the current upload to finish.");
      return;
    }
    const input = createDeckUploadInput({ allowDirectories: true });
    const handleChange = (event) => {
      handleDeckUploadSelection(event);
      input.removeEventListener("change", handleChange);
      if (input.parentNode) {
        input.parentNode.removeChild(input);
      }
    };
    input.addEventListener("change", handleChange);
    input.click();
  }

  function triggerDeckZipUpload() {
    if (state.uploading) {
      reportStatus("Please wait for the current upload to finish.");
      return;
    }
    const input = createDeckUploadInput({ allowDirectories: false });
    const handleChange = (event) => {
      handleDeckUploadSelection(event);
      input.removeEventListener("change", handleChange);
      if (input.parentNode) {
        input.parentNode.removeChild(input);
      }
    };
    input.addEventListener("change", handleChange);
    input.click();
  }

  function handleDeckUploadSelection(event) {
    const files = Array.from((event && event.target && event.target.files) || []);
    if (!files.length) {
      return;
    }
    const defaultId = inferDeckIdFromFiles(files);
    const deckId = promptDeckId(defaultId);
    if (!deckId) {
      return;
    }
    uploadDeckFiles(deckId, files);
  }

  function createDeckUploadInput(options = {}) {
    const { allowDirectories = true } = options;
    const input = document.createElement("input");
    input.type = "file";
    if (allowDirectories) {
      input.accept = ".zip,.html,.htm,.json,.css,.js,.png,.jpg,.jpeg,.gif,.svg,.webp,.woff,.woff2,.ttf,.txt";
      input.multiple = true;
      input.setAttribute("webkitdirectory", "");
      input.setAttribute("directory", "");
      input.setAttribute("mozdirectory", "");
    } else {
      input.accept = ".zip";
      input.multiple = false;
    }
    input.style.display = "none";
    input.tabIndex = -1;
    input.setAttribute("aria-hidden", "true");
    document.body.appendChild(input);
    return input;
  }

  function promptDeckId(defaultId) {
    const provided = window.prompt("Name for the uploaded deck", defaultId || "deck");
    if (!provided) {
      return null;
    }
    const trimmed = provided.trim();
    return trimmed || null;
  }

  function inferDeckIdFromFiles(files) {
    if (!files.length) {
      return `deck-${Date.now()}`;
    }
    const first = files[0];
    const path = first.webkitRelativePath || first.name || "deck";
    let base = path.split("/")[0] || path;
    if (!first.webkitRelativePath && base.includes(".")) {
      base = base.replace(/\.[^.]+$/, "");
    }
    base = base.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
    if (!base) {
      base = `deck-${Date.now()}`;
    }
    return base;
  }

  function setUploading(isUploading) {
    state.uploading = isUploading;
    if (elements.uploadDeckBtn) {
      elements.uploadDeckBtn.disabled = isUploading;
    }
    if (elements.uploadDeckZipBtn) {
      elements.uploadDeckZipBtn.disabled = isUploading;
    }
  }

  function setPrinting(isPrinting) {
    state.printing = isPrinting;
    if (elements.printDeckBtn) {
      elements.printDeckBtn.disabled = isPrinting || !state.currentDeckId;
    }
    if (!isPrinting && state.printJobTimer) {
      clearTimeout(state.printJobTimer);
      state.printJobTimer = null;
    }
  }

  function uploadDeckFiles(deckId, files) {
    if (!files.length) {
      return;
    }
    setUploading(true);
    reportStatus(`Uploading ${deckId}…`);
    const formData = new FormData();
    formData.append("deckId", deckId);
    files.forEach((file) => {
      const name = file.webkitRelativePath || file.name;
      formData.append("files", file, name);
    });
    fetchJson("/slides/deck/upload", {
      method: "POST",
      body: formData,
    })
      .then((deck) => {
        applyDeckResponse(deck);
        reportStatus(`Uploaded deck ${deck.deckId}.`);
      })
      .catch((error) => {
        console.error("Deck upload failed", error);
        reportStatus(formatDeckUploadError(error), true);
      })
      .finally(() => {
        setUploading(false);
      });
  }

  function fetchJson(url, options = {}) {
    return fetch(url, options).then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
          const data = JSON.parse(text);
          message = data.detail || data.message || JSON.stringify(data);
        } catch (error) {
          // ignore JSON parse errors
        }
        const error = new Error(message || response.statusText || "Request failed");
        error.status = response.status;
        error.statusText = response.statusText;
        throw error;
      }
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        return response.json();
      }
      return {};
    });
  }

  function reportStatus(message, isError = false) {
    if (!elements.status) {
      return;
    }
    elements.status.textContent = message || "";
    elements.status.classList.toggle("is-error", Boolean(isError));
  }

  function updateTagButtonState() {
    if (!elements.tagSlidesBtn) {
      return;
    }
    const disabled =
      !state.currentDeckId ||
      state.tagging ||
      state.uploading ||
      state.concatenating ||
      state.printing ||
      !state.slides.length;
    elements.tagSlidesBtn.disabled = disabled;

    if (elements.deckSelect) {
      const tagAllHint = elements.deckSelect.dataset.tagAllLabel || "";
      if (!state.selectedSlideIds || !state.selectedSlideIds.length) {
        elements.tagSummary.textContent = tagAllHint;
        elements.tagSummary.hidden = !tagAllHint;
      }
    }
  }

  function renderTagSummary(data) {
    if (!elements.tagSummary) {
      return;
    }
    if (!data) {
      elements.tagSummary.hidden = true;
      elements.tagSummary.textContent = "";
      return;
    }
    const details = [
      `Tagged: ${data.tagged}`,
      `Skipped: ${data.skipped}`,
      `Metric duplicate clusters: ${data.metricClusters}`,
      `Recommendation duplicate clusters: ${data.recoClusters}`,
      `Unlinked recommendations: ${data.unlinked}`,
    ];
    if (data.issueCount) {
      details.push(`Slides with issues: ${data.issueCount}`);
    }
    elements.tagSummary.textContent = details.join(" · ");
    elements.tagSummary.hidden = false;
  }

  function setCurrentTagJob(jobId) {
    state.currentTagJobId = jobId;
    try {
        localStorage.setItem(`tagJob:${state.currentDeckId}`, jobId);
    } catch (e) {
      // ignore storage errors
    }
  }

  function clearCurrentTagJob() {
    const key = `tagJob:${state.currentDeckId}`;
    state.currentTagJobId = null;
    try {
      localStorage.removeItem(key);
    } catch (e) {
      // ignore storage errors
    }
  }

  function resumeTagJobIfNeeded() {
    // Auto-resume disabled; tagging jobs are handled via email notification or manual refresh.
    clearCurrentTagJob();
  }

  function stripHtml(html) {
    if (!html) {
      return "";
    }
    const parser = new DOMParser();
    const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
    return doc.body.textContent || "";
  }

  function normalizeDeckSummary(deck) {
    return {
      deckId: deck.deckId,
      slides: Array.isArray(deck.slides) ? deck.slides.map(normalizeSlide) : [],
      sections: Array.isArray(deck.sections) ? cloneSections(deck.sections) : [],
    };
  }

  function normalizeSlide(slide) {
    if (!slide) {
      return {
        id: "",
        titleHtml: "",
        bodyHtml: "",
        notesHtml: "",
        sourceHtml: "",
        fullHtml: "",
        kind: "normal",
        sectionId: null,
        subsectionId: null,
      };
    }
    const kind = slide.kind === "sectionHeader" ? "sectionHeader" : "normal";
    return {
      id: slide.id,
      titleHtml: slide.titleHtml || "",
      bodyHtml: slide.bodyHtml || "",
      notesHtml: slide.notesHtml || "",
      sourceHtml: slide.sourceHtml || "",
      fullHtml: slide.fullHtml || "",
      kind,
      sectionId: slide.sectionId || null,
      subsectionId: slide.subsectionId || null,
    };
  }

  function normalizeSection(section) {
    const subsections = Array.isArray(section.subsections)
      ? section.subsections.map((sub) => ({
          id: sub.id || "",
          title: sub.title || "",
          startSlide: sub.startSlide || "",
        }))
      : [];
    return {
      id: section.id || "",
      title: section.title || "",
      startSlide: section.startSlide || "",
      subsections,
    };
  }

  function cloneSections(sections) {
    return (sections || []).map((section) => {
      const normalised = normalizeSection(section);
      return {
        ...normalised,
        subsections: normalised.subsections.map((sub) => ({ ...sub })),
      };
    });
  }

  function addSection() {
    if (!state.slides.length) {
      reportStatus("Add at least one slide before creating sections.", true);
      return;
    }
    const baseIndex = state.sections.length + 1;
    const defaultId = `Section${baseIndex}`;
    const firstSlide = findFirstContentSlide();
    const newSection = {
      id: defaultId,
      title: defaultId,
      startSlide: firstSlide,
      subsections: [],
    };
    state.sections.push(newSection);
    state.dirty = true;
    syncSectionHeaderSlides();
    syncDeckSummary();
    renderSectionsPanel();
    renderSlideList();
  }

  function renderSectionsPanel() {
    if (!elements.sectionsList) {
      return;
    }
    elements.sectionsList.innerHTML = "";
    state.sections.forEach((section, index) => {
      elements.sectionsList.appendChild(createSectionCard(section, index));
    });
  }

  function createSectionCard(section, index) {
    const card = document.createElement("div");
    card.className = "slides-editor__section-card";

    const header = document.createElement("div");
    header.className = "slides-editor__section-header";
    const headerTitle = document.createElement("strong");
    headerTitle.textContent = section.title || section.id || `Section ${index + 1}`;
    header.appendChild(headerTitle);
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeSection(index));
    header.appendChild(removeBtn);
    card.appendChild(header);

    const fields = document.createElement("div");
    fields.className = "slides-editor__section-fields";

    const idLabel = document.createElement("label");
    const idSpan = document.createElement("span");
    idSpan.textContent = "ID";
    idLabel.appendChild(idSpan);
    const idInput = document.createElement("input");
    idInput.value = section.id;
    idInput.addEventListener("change", (event) => {
      const newId = event.target.value.trim();
      if (!newId) {
        event.target.value = section.id;
        return;
      }
      updateSectionId(index, newId);
      headerTitle.textContent = section.title || section.id || `Section ${index + 1}`;
      event.target.value = section.id;
    });
    idLabel.appendChild(idInput);
    fields.appendChild(idLabel);

    const titleLabel = document.createElement("label");
    const titleSpan = document.createElement("span");
    titleSpan.textContent = "Title";
    titleLabel.appendChild(titleSpan);
    const titleInput = document.createElement("input");
    titleInput.value = section.title;
    titleInput.addEventListener("input", (event) => {
      section.title = event.target.value;
      headerTitle.textContent = section.title || section.id || `Section ${index + 1}`;
      state.dirty = true;
      syncSectionHeaderSlides();
      syncDeckSummary();
      renderSlideList();
    });
    titleLabel.appendChild(titleInput);
    fields.appendChild(titleLabel);

    const startLabel = document.createElement("label");
    const startSpan = document.createElement("span");
    startSpan.textContent = "Starts at";
    startLabel.appendChild(startSpan);
    const startSelect = createSlideSelect(section.startSlide, (value) => {
      section.startSlide = value;
      state.dirty = true;
      syncDeckSummary();
    });
    startLabel.appendChild(startSelect);
    fields.appendChild(startLabel);
    card.appendChild(fields);

    const actions = document.createElement("div");
    actions.className = "slides-editor__section-actions";
    const insertBtn = document.createElement("button");
    insertBtn.type = "button";
    insertBtn.textContent = "Insert header";
    applyTooltip(
      insertBtn,
      "insert_header",
      "Insert a section-header slide for this section."
    );
    insertBtn.addEventListener("click", () => insertSectionHeader(section.id, null));
    actions.appendChild(insertBtn);
    const convertBtn = createSectionHeaderConvertButton(section.id, null);
    actions.appendChild(convertBtn);
    const addSubBtn = document.createElement("button");
    addSubBtn.type = "button";
    addSubBtn.textContent = "Add subsection";
    applyTooltip(
      addSubBtn,
      "add_subsection",
      "Create a subsection that links to a specific slide in this section."
    );
    addSubBtn.addEventListener("click", () => addSubsection(index));
    actions.appendChild(addSubBtn);
    card.appendChild(actions);

    if (section.subsections.length) {
      const subsContainer = document.createElement("div");
      subsContainer.className = "slides-editor__subsections";
      section.subsections.forEach((subsection, subIndex) => {
        subsContainer.appendChild(createSubsectionCard(section, index, subsection, subIndex));
      });
      card.appendChild(subsContainer);
    }

    return card;
  }

  function createSubsectionCard(section, sectionIndex, subsection, subIndex) {
    const card = document.createElement("div");
    card.className = "slides-editor__subsection-card";

    const title = document.createElement("strong");
    title.textContent = subsection.title || subsection.id || `Subsection ${subIndex + 1}`;
    card.appendChild(title);

    const fields = document.createElement("div");
    fields.className = "slides-editor__section-fields";

    const idLabel = document.createElement("label");
    const idSpan = document.createElement("span");
    idSpan.textContent = "ID";
    idLabel.appendChild(idSpan);
    const idInput = document.createElement("input");
    idInput.value = subsection.id;
    idInput.addEventListener("change", (event) => {
      const newId = event.target.value.trim();
      if (!newId) {
        event.target.value = subsection.id;
        return;
      }
      updateSubsectionId(sectionIndex, subIndex, newId);
      title.textContent = subsection.title || subsection.id || `Subsection ${subIndex + 1}`;
      event.target.value = subsection.id;
    });
    idLabel.appendChild(idInput);
    fields.appendChild(idLabel);

    const titleLabel = document.createElement("label");
    const titleSpan = document.createElement("span");
    titleSpan.textContent = "Title";
    titleLabel.appendChild(titleSpan);
    const titleInput = document.createElement("input");
    titleInput.value = subsection.title;
    titleInput.addEventListener("input", (event) => {
      subsection.title = event.target.value;
      title.textContent = subsection.title || subsection.id || `Subsection ${subIndex + 1}`;
      state.dirty = true;
      syncSectionHeaderSlides();
      syncDeckSummary();
      renderSlideList();
    });
    titleLabel.appendChild(titleInput);
    fields.appendChild(titleLabel);

    const startLabel = document.createElement("label");
    const startSpan = document.createElement("span");
    startSpan.textContent = "Starts at";
    startLabel.appendChild(startSpan);
    const startSelect = createSlideSelect(subsection.startSlide, (value) => {
      subsection.startSlide = value;
      state.dirty = true;
      syncDeckSummary();
    });
    startLabel.appendChild(startSelect);
    fields.appendChild(startLabel);
    card.appendChild(fields);

    const actions = document.createElement("div");
    actions.className = "slides-editor__section-actions";
    const insertBtn = document.createElement("button");
    insertBtn.type = "button";
    insertBtn.textContent = "Insert header";
    applyTooltip(
      insertBtn,
      "insert_header",
      "Insert a section-header slide for this subsection."
    );
    insertBtn.addEventListener("click", () => insertSectionHeader(section.id, subsection.id));
    actions.appendChild(insertBtn);
    const convertBtn = createSectionHeaderConvertButton(section.id, subsection.id);
    actions.appendChild(convertBtn);
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeSubsection(sectionIndex, subIndex));
    actions.appendChild(removeBtn);
    card.appendChild(actions);

    return card;
  }

  function createSlideSelect(currentValue, onChange) {
    const select = document.createElement("select");
    const slides = state.slides.filter((slide) => slide.kind !== "sectionHeader");
    if (!slides.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No slides";
      select.appendChild(option);
      select.disabled = true;
      return select;
    }
    slides.forEach((slide) => {
      const option = document.createElement("option");
      option.value = slide.id;
      option.textContent = stripHtml(slide.titleHtml) || slide.id;
      select.appendChild(option);
    });
    if (currentValue && slides.some((slide) => slide.id === currentValue)) {
      select.value = currentValue;
    } else {
      select.value = slides[0].id;
      if (onChange) {
        onChange(select.value);
      }
    }
    if (onChange) {
      select.addEventListener("change", (event) => onChange(event.target.value));
    }
    return select;
  }

  function createSectionHeaderConvertButton(sectionId, subsectionId) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Use selection as header";
    button.disabled = !canPromoteSelectedSlide();
    button.addEventListener("click", () => setSlideAsSectionHeader(sectionId, subsectionId || null));
    applyTooltip(
      button,
      "use_selection_as_header",
      "Convert the selected slide into a section header for this group."
    );
    return button;
  }

  function addSubsection(sectionIndex) {
    const section = state.sections[sectionIndex];
    if (!section) {
      return;
    }
    const baseIndex = section.subsections.length + 1;
    const defaultId = `${section.id || "Sub"}${baseIndex}`;
    const newSubsection = {
      id: defaultId,
      title: defaultId,
      startSlide: section.startSlide || findFirstContentSlide(),
    };
    section.subsections.push(newSubsection);
    state.dirty = true;
    syncSectionHeaderSlides();
    syncDeckSummary();
    renderSectionsPanel();
    renderSlideList();
  }

  function removeSection(index) {
    const [removed] = state.sections.splice(index, 1);
    if (!removed) {
      return;
    }
    state.slides = state.slides.filter((slide) => {
      if (slide.kind !== "sectionHeader") {
        return true;
      }
      return slide.sectionId !== removed.id;
    });
    ensureSelectionIntegrity();
    state.dirty = true;
    syncSectionHeaderSlides();
    syncDeckSummary();
    renderSectionsPanel();
    renderSlideList();
    renderSelection();
  }

  function removeSubsection(sectionIndex, subIndex) {
    const section = state.sections[sectionIndex];
    if (!section) {
      return;
    }
    const [removed] = section.subsections.splice(subIndex, 1);
    if (!removed) {
      return;
    }
    state.slides = state.slides.filter((slide) => {
      if (slide.kind !== "sectionHeader") {
        return true;
      }
      return !(slide.sectionId === section.id && slide.subsectionId === removed.id);
    });
    ensureSelectionIntegrity();
    state.dirty = true;
    syncSectionHeaderSlides();
    syncDeckSummary();
    renderSectionsPanel();
    renderSlideList();
    renderSelection();
  }

  function updateSectionId(index, newId) {
    const section = state.sections[index];
    if (!section || section.id === newId) {
      return;
    }
    const previousId = section.id;
    section.id = newId;
    state.slides.forEach((slide) => {
      if (slide.kind === "sectionHeader" && slide.sectionId === previousId) {
        slide.sectionId = newId;
      }
    });
    state.dirty = true;
    syncSectionHeaderSlides();
    syncDeckSummary();
    renderSlideList();
  }

  function updateSubsectionId(sectionIndex, subIndex, newId) {
    const section = state.sections[sectionIndex];
    if (!section) {
      return;
    }
    const subsection = section.subsections[subIndex];
    if (!subsection || subsection.id === newId) {
      return;
    }
    const previousId = subsection.id;
    subsection.id = newId;
    state.slides.forEach((slide) => {
      if (
        slide.kind === "sectionHeader" &&
        slide.sectionId === section.id &&
        slide.subsectionId === previousId
      ) {
        slide.subsectionId = newId;
      }
    });
    state.dirty = true;
    syncSectionHeaderSlides();
    syncDeckSummary();
    renderSlideList();
  }

  function insertSectionHeader(sectionId, subsectionId) {
    if (!sectionId) {
      return;
    }
    const section = findSection(sectionId);
    if (!section) {
      reportStatus(`Unknown section ${sectionId}`, true);
      return;
    }
    const target = subsectionId
      ? findSubsection(section, subsectionId)?.startSlide
      : section.startSlide;
    if (!target) {
      reportStatus("Select a start slide before inserting a header.", true);
      return;
    }
    const index = state.slides.findIndex((slide) => slide.id === target);
    const header = normalizeSlide({
      id: nextSlideId(),
      titleHtml: "",
      bodyHtml: "",
      kind: "sectionHeader",
      sectionId,
      subsectionId: subsectionId || null,
    });
    applySectionHeaderTemplate(header);
    if (index === -1) {
      state.slides.push(header);
    } else {
      state.slides.splice(index, 0, header);
    }
    commitSelection([header.id], header.id, header.id);
    state.dirty = true;
    syncDeckSummary();
    syncSectionHeaderSlides();
    renderSlideList();
    renderSelection();
  }

  function setSlideAsSectionHeader(sectionId, subsectionId) {
    if (!sectionId) {
      return;
    }
    const slide = getSelectedSlide();
    if (!slide || slide.kind === "sectionHeader") {
      return;
    }
    const section = findSection(sectionId);
    if (!section) {
      reportStatus(`Unknown section ${sectionId}`, true);
      return;
    }
    let targetSlideId = section.startSlide || null;
    if (subsectionId) {
      const subsection = findSubsection(section, subsectionId);
      if (!subsection) {
        reportStatus(`Unknown subsection ${subsectionId}`, true);
        return;
      }
      targetSlideId = subsection.startSlide || targetSlideId;
    }
    slide.kind = "sectionHeader";
    slide.sectionId = sectionId;
    slide.subsectionId = subsectionId || null;
    slide.titleHtml = "";
    slide.bodyHtml = "";
    applySectionHeaderTemplate(slide);
    if (targetSlideId && targetSlideId !== slide.id) {
      const currentIndex = state.slides.findIndex((item) => item.id === slide.id);
      if (currentIndex !== -1) {
        const [removed] = state.slides.splice(currentIndex, 1);
        const destinationIndex = state.slides.findIndex((item) => item.id === targetSlideId);
        if (destinationIndex !== -1) {
          state.slides.splice(destinationIndex, 0, removed);
        } else {
          state.slides.splice(currentIndex, 0, removed);
        }
      }
    }
    state.dirty = true;
    syncDeckSummary();
    syncSectionHeaderSlides();
    renderSlideList();
    renderSelection();
    reportStatus(`Converted ${slide.id} to a section header.`);
  }

  function syncSectionHeaderSlides() {
    state.slides.forEach((slide) => {
      if (slide.kind === "sectionHeader") {
        applySectionHeaderTemplate(slide);
      }
    });
  }

  function applySectionHeaderTemplate(slide) {
    if (!slide) {
      return;
    }
    const content = computeSectionHeaderContent(slide.sectionId, slide.subsectionId);
    slide.titleHtml = content.titleHtml;
    slide.bodyHtml = content.bodyHtml;
  }

  function computeSectionHeaderContent(sectionId, subsectionId) {
    if (!sectionId || !state.sections.length) {
      return {
        titleHtml: "",
        bodyHtml:
          '<section class="section-header"><p class="section-header__placeholder">Define sections to see a preview.</p></section>',
      };
    }
    const section = findSection(sectionId);
    if (!section) {
      return {
        titleHtml: "",
        bodyHtml: `<section class="section-header"><p class="section-header__placeholder">Unknown section ${escapeHtml(
          sectionId
        )}</p></section>`,
      };
    }
    const titleText = section.title || section.id;
    const sectionItems = state.sections
      .map((entry) => renderSectionItem(entry, sectionId, subsectionId))
      .join("");
    return {
      titleHtml: `<span class="section-header__title-text">${escapeHtml(titleText)}</span>`,
      bodyHtml: `<section class="section-header"><ol class="section-header__sections">${sectionItems}</ol></section>`,
    };
  }

  function renderSectionItem(section, currentSectionId, currentSubsectionId) {
    const classes = ["section-header__section"];
    const isCurrent = section.id === currentSectionId;
    if (isCurrent) {
      classes.push("is-current");
    }
    const subsections = renderSubsectionList(
      section,
      currentSubsectionId,
      isCurrent
    );
    return `<li class="${classes.join(" ")}"><span class="section-header__section-label">${escapeHtml(
      section.title || section.id
    )}</span>${subsections}</li>`;
  }

  function renderSubsectionList(section, currentSubsectionId, isCurrent) {
    if (!Array.isArray(section.subsections) || !section.subsections.length) {
      return "";
    }
    const items = section.subsections
      .map((sub) => {
        const classes = ["section-header__subsection"];
        if (isCurrent && sub.id === currentSubsectionId) {
          classes.push("is-current");
        }
        return `<li class="${classes.join(" ")}">${escapeHtml(
          sub.title || sub.id
        )}</li>`;
      })
      .join("");
    return `<ul class="section-header__subsections">${items}</ul>`;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  const DEFAULT_SLIDE_DOCUMENT = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title></title>
  </head>
  <body>
    <div class="slide-container">
      <h1 class="slide-title" data-role="title"></h1>
      <div class="slide-body"></div>
      <aside class="slide-notes"></aside>
      <footer class="slide-source"></footer>
    </div>
  </body>
</html>`;

  function buildSlidePreviewDocument(slide) {
    if (!slide) {
      return buildPreviewFallbackDocument(slide);
    }
    const doc = createSlidePreviewDocument(slide);
    if (!doc) {
      return buildPreviewFallbackDocument(slide);
    }
    ensurePreviewMeta(doc);
    injectPreviewBaseStyles(doc);
    sanitizeExternalResources(doc);
    injectPreviewBundles(doc);
    return `<!DOCTYPE html>\n${doc.documentElement.outerHTML}`;
  }

  function buildPreviewFallbackDocument(slide) {
    const titleHtml = formatPreviewHtml(slide ? slide.titleHtml : "", "Add a title");
    const bodyHtml = formatPreviewHtml(slide ? slide.bodyHtml : "", "Start adding content");
    return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <style>
      :root {
        font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
      }
      html,
      body {
        min-height: 100%;
      }
      body {
        margin: 0;
        background: #f8fafc;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        padding: 24px;
      }
      .preview-stage {
        flex: 1 1 auto;
        width: 100%;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        max-width: 100%;
        padding: 24px;
        box-sizing: border-box;
      }
      .preview-stage__inner {
        width: 100%;
        max-width: 960px;
        display: flex;
        align-items: stretch;
        justify-content: center;
      }
      .preview-slide {
        background: #ffffff;
        border: 1px solid #d0d5dd;
        border-radius: 16px;
        box-shadow: 0 20px 45px rgba(15, 23, 42, 0.12);
        width: auto;
        max-width: 960px;
        min-height: auto;
        padding: 48px;
        display: flex;
        flex-direction: column;
        gap: 28px;
        box-sizing: border-box;
      }
      .preview-slide__title {
        font-size: 30px;
        font-weight: 600;
        color: #0f172a;
        margin: 0;
      }
      .preview-slide__body {
        font-size: 17px;
        line-height: 1.6;
        color: #111827;
      }
      .preview-placeholder {
        color: #94a3b8;
        font-style: italic;
      }
    </style>
  </head>
  <body>
    <div class="preview-stage">
      <div class="preview-stage__inner">
        <section class="preview-slide">
          <h1 class="preview-slide__title">${titleHtml}</h1>
          <div class="preview-slide__body">${bodyHtml}</div>
        </section>
      </div>
    </div>
  </body>
</html>`;
  }

  function createSlidePreviewDocument(slide) {
    const parser = new DOMParser();
    const source = (slide.fullHtml || "").trim();
    let doc = null;
    if (!source) {
      return null;
    }
    doc = safeParseHtml(parser, source);
    if (!doc) {
      doc = safeParseHtml(parser, DEFAULT_SLIDE_DOCUMENT);
    }
    if (!doc) {
      return null;
    }
    updateSlideContent(doc, slide);
    return doc;
  }

  function safeParseHtml(parser, html) {
    try {
      const doc = parser.parseFromString(html, "text/html");
      if (!doc || doc.querySelector("parsererror")) {
        return null;
      }
      return doc;
    } catch (error) {
      return null;
    }
  }

  function updateSlideContent(doc, slide) {
    const body = doc.body || doc.createElement("body");
    if (!doc.body) {
      doc.documentElement.appendChild(body);
    }
    const container = findOrCreateSlideContainer(doc, body);
    const titleElement = findOrCreateTitleElement(doc, container);
    if (titleElement) {
      titleElement.innerHTML = formatPreviewHtml(slide.titleHtml, "Add a title");
    }
    const bodyElement = findOrCreateBodyElement(doc, container, titleElement);
    if (bodyElement) {
      bodyElement.innerHTML = formatPreviewHtml(slide.bodyHtml, "Start adding content");
    }
    const notesElement = findOrCreateNotesElement(doc, container);
    if (notesElement) {
      notesElement.innerHTML = slide.notesHtml || "";
    }
    const sourceElement = findOrCreateSourceElement(doc, container);
    if (sourceElement) {
      sourceElement.innerHTML = slide.sourceHtml || "";
    }
  }

  function findOrCreateSlideContainer(doc, body) {
    const existing = body.querySelector(".slide-container");
    if (existing) {
      return existing;
    }
    const container = doc.createElement("div");
    container.className = "slide-container";
    body.appendChild(container);
    return container;
  }

  function findOrCreateTitleElement(doc, container) {
    const title =
      container.querySelector('[data-role="title"]') ||
      container.querySelector(".slide-title") ||
      container.querySelector(".title") ||
      container.querySelector("h1") ||
      container.querySelector("h2");
    if (title) {
      if (!title.getAttribute("data-role")) {
        title.setAttribute("data-role", "title");
      }
      return title;
    }
    const created = doc.createElement("h1");
    created.className = "slide-title";
    created.setAttribute("data-role", "title");
    container.insertBefore(created, container.firstChild || null);
    return created;
  }

  function findOrCreateBodyElement(doc, container, titleElement) {
    const body = container.querySelector(".slide-body");
    if (body) {
      return body;
    }
    const created = doc.createElement("div");
    created.className = "slide-body";
    if (titleElement && titleElement.nextSibling) {
      container.insertBefore(created, titleElement.nextSibling);
    } else {
      container.appendChild(created);
    }
    return created;
  }

  function findOrCreateNotesElement(doc, container) {
    const notes = container.querySelector("aside.slide-notes");
    if (notes) {
      return notes;
    }
    const created = doc.createElement("aside");
    created.className = "slide-notes";
    container.appendChild(created);
    return created;
  }

  function findOrCreateSourceElement(doc, container) {
    const source = container.querySelector("footer.slide-source");
    if (source) {
      return source;
    }
    const created = doc.createElement("footer");
    created.className = "slide-source";
    container.appendChild(created);
    return created;
  }

  function ensurePreviewMeta(doc) {
    let head = doc.head;
    if (!head) {
      head = doc.createElement("head");
      if (doc.documentElement.firstChild) {
        doc.documentElement.insertBefore(head, doc.documentElement.firstChild);
      } else {
        doc.documentElement.appendChild(head);
      }
    }
    if (!head.querySelector("meta[charset]")) {
      const meta = doc.createElement("meta");
      meta.setAttribute("charset", "utf-8");
      head.insertBefore(meta, head.firstChild || null);
    }
  }

  function injectPreviewBaseStyles(doc) {
    if (!doc) {
      return;
    }
    let head = doc.head;
    if (!head) {
      head = doc.createElement("head");
      doc.documentElement.insertBefore(head, doc.documentElement.firstChild || null);
    }
    const existing = head.querySelector('style[data-preview-style="base"]');
    if (existing) {
      existing.remove();
    }
    const style = doc.createElement("style");
    style.setAttribute("data-preview-style", "base");
    style.textContent = `
      :root {
        box-sizing: border-box;
      }
      *, *::before, *::after {
        box-sizing: inherit;
      }
      html,
      body {
        width: 100%;
        min-height: 100%;
        margin: 0;
        padding: 0;
      }
      body {
        display: flex;
        align-items: stretch;
        justify-content: stretch;
        background: transparent;
      }
      .slide-container {
        width: 100%;
        min-height: 100%;
        flex: 1 1 auto;
        margin: 0;
        max-width: none !important;
      }
      .slide-container > * {
        max-width: 100%;
      }
      img,
      picture,
      video,
      svg,
      canvas {
        max-width: 100%;
        height: auto;
      }
    `;
    head.appendChild(style);
  }

  function sanitizeExternalResources(doc) {
    const config = getPreviewConfig();
    const allowedOrigins = config.allowedOrigins || new Set();
    doc.querySelectorAll('link[rel~="stylesheet"][href]').forEach((link) => {
      const href = link.getAttribute("href");
      if (!isAllowedResourceUrl(href, allowedOrigins)) {
        link.remove();
      }
    });
    doc.querySelectorAll("script[src]").forEach((script) => {
      const src = script.getAttribute("src");
      if (!isAllowedResourceUrl(src, allowedOrigins)) {
        script.remove();
      }
    });
  }

  function isAllowedResourceUrl(url, allowedOrigins) {
    if (!url) {
      return false;
    }
    const trimmed = url.trim();
    if (!trimmed || /^javascript:/i.test(trimmed)) {
      return false;
    }
    if (/^data:/i.test(trimmed)) {
      return true;
    }
    try {
      const parsed = new URL(trimmed, window.location.origin);
      if (!parsed.protocol || !(parsed.protocol === "http:" || parsed.protocol === "https:")) {
        return false;
      }
      if (parsed.origin === window.location.origin) {
        return true;
      }
      return allowedOrigins.has(parsed.origin);
    } catch (error) {
      return false;
    }
  }

  function injectPreviewBundles(doc) {
    const config = getPreviewConfig();
    const styles = config.styles || [];
    const scripts = config.scripts || [];
    let head = doc.head;
    if (!head) {
      head = doc.createElement("head");
      doc.documentElement.insertBefore(head, doc.documentElement.firstChild || null);
    }
    styles.forEach((href) => {
      if (!href || hasExistingStylesheet(doc, href)) {
        return;
      }
      const link = doc.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.setAttribute("data-preview-bundle", "style");
      head.appendChild(link);
    });
    const body = doc.body || doc.createElement("body");
    if (!doc.body) {
      doc.documentElement.appendChild(body);
    }
    scripts.forEach((src) => {
      if (!src || hasExistingScript(doc, src)) {
        return;
      }
      const script = doc.createElement("script");
      script.src = src;
      script.defer = true;
      script.setAttribute("data-preview-bundle", "script");
      body.appendChild(script);
    });
  }

  function hasExistingStylesheet(doc, href) {
    const target = href.trim();
    if (!target) {
      return true;
    }
    return Array.from(doc.querySelectorAll('link[rel~="stylesheet"]')).some((link) => {
      return (link.getAttribute("href") || "").trim() === target;
    });
  }

  function hasExistingScript(doc, src) {
    const target = src.trim();
    if (!target) {
      return true;
    }
    return Array.from(doc.querySelectorAll("script[src]")).some((script) => {
      return (script.getAttribute("src") || "").trim() === target;
    });
  }

  function formatPreviewHtml(html, placeholderText) {
    const trimmed = (html || "").trim();
    if (trimmed) {
      return trimmed;
    }
    return `<span class="preview-placeholder">${escapeHtml(placeholderText)}</span>`;
  }

  function getSlideLabel(slide) {
    if (slide.kind !== "sectionHeader") {
      return stripHtml(slide.titleHtml) || slide.id;
    }
    if (!slide.sectionId) {
      return `Section header (${slide.id})`;
    }
    const section = findSection(slide.sectionId);
    if (!section) {
      return `Section ${slide.sectionId} header`;
    }
    if (slide.subsectionId) {
      const subsection = findSubsection(section, slide.subsectionId);
      const subTitle = subsection ? subsection.title || subsection.id : slide.subsectionId;
      return `Header · ${section.title || section.id} / ${subTitle}`;
    }
    return `Header · ${section.title || section.id}`;
  }

  function findSection(sectionId) {
    return state.sections.find((section) => section.id === sectionId) || null;
  }

  function findSubsection(section, subsectionId) {
    if (!section || !Array.isArray(section.subsections)) {
      return null;
    }
    return section.subsections.find((sub) => sub.id === subsectionId) || null;
  }

  function findFirstContentSlide() {
    const firstContent = state.slides.find((slide) => slide.kind !== "sectionHeader");
    if (firstContent) {
      return firstContent.id;
    }
    return state.slides.length ? state.slides[0].id : "";
  }

  function handleSlideRemoval(removedSlide, removalIndex) {
    if (!removedSlide) {
      return;
    }
    if (removedSlide.kind === "sectionHeader") {
      return;
    }
    const fallback = findContentSlideAfter(removalIndex);
    let sectionsChanged = false;
    state.sections = state.sections
      .map((section) => {
        const updated = { ...section, subsections: section.subsections.map((sub) => ({ ...sub })) };
        if (updated.startSlide === removedSlide.id) {
          if (fallback) {
            updated.startSlide = fallback;
            sectionsChanged = true;
          } else {
            sectionsChanged = true;
            return null;
          }
        }
        updated.subsections = updated.subsections.filter((subsection) => {
          if (subsection.startSlide !== removedSlide.id) {
            return true;
          }
          if (fallback) {
            subsection.startSlide = fallback;
            sectionsChanged = true;
            return true;
          }
          sectionsChanged = true;
          return false;
        });
        return updated;
      })
      .filter(Boolean);
    if (sectionsChanged) {
      state.dirty = true;
      syncSectionHeaderSlides();
      syncDeckSummary();
      cleanupSectionHeaders();
      renderSectionsPanel();
    }
  }

  function findContentSlideAfter(startIndex) {
    for (let idx = startIndex; idx < state.slides.length; idx += 1) {
      const candidate = state.slides[idx];
      if (candidate && candidate.kind !== "sectionHeader") {
        return candidate.id;
      }
    }
    for (let idx = startIndex - 1; idx >= 0; idx -= 1) {
      const candidate = state.slides[idx];
      if (candidate && candidate.kind !== "sectionHeader") {
        return candidate.id;
      }
    }
    return null;
  }

  function cleanupSectionHeaders() {
    const sectionIds = new Set(state.sections.map((section) => section.id));
    state.slides = state.slides.filter((slide) => {
      if (slide.kind !== "sectionHeader") {
        return true;
      }
      if (!slide.sectionId || !sectionIds.has(slide.sectionId)) {
        return false;
      }
      if (slide.subsectionId) {
        const section = findSection(slide.sectionId);
        if (!section || !section.subsections.some((sub) => sub.id === slide.subsectionId)) {
          slide.subsectionId = null;
        }
      }
      return true;
    });
    ensureSelectionIntegrity();
  }

  function getPreviewConfig() {
    if (previewConfig) {
      return previewConfig;
    }
    previewConfig = createPreviewConfig();
    return previewConfig;
  }

  function createPreviewConfig() {
    const root = document.querySelector(".slides-editor");
    const dataset = (root && root.dataset) || {};
    const styles = mergeUniqueValues(
      DEFAULT_PREVIEW_STYLE_BUNDLES,
      parseDataList(dataset.previewStyles)
    );
    const scripts = mergeUniqueValues(
      DEFAULT_PREVIEW_SCRIPT_BUNDLES,
      parseDataList(dataset.previewScripts)
    );
    const allowedOrigins = new Set();
    DEFAULT_ALLOWED_PREVIEW_ORIGINS.forEach((origin) => {
      const normalized = normalizeOrigin(origin);
      if (normalized) {
        allowedOrigins.add(normalized);
      }
    });
    parseDataList(dataset.previewAllowlist).forEach((origin) => {
      const normalized = normalizeOrigin(origin);
      if (normalized) {
        allowedOrigins.add(normalized);
      }
    });
    return { styles, scripts, allowedOrigins };
  }

  function parseDataList(value) {
    if (!value) {
      return [];
    }
    return value
      .split(/[,\s]+/)
      .map((entry) => entry.trim())
      .filter(Boolean);
  }

  function mergeUniqueValues(defaultValues, extraValues) {
    const seen = new Set();
    const merged = [];
    [...(defaultValues || []), ...(extraValues || [])].forEach((entry) => {
      const trimmed = (entry || "").trim();
      if (!trimmed || seen.has(trimmed)) {
        return;
      }
      seen.add(trimmed);
      merged.push(trimmed);
    });
    return merged;
  }

  function normalizeOrigin(value) {
    if (!value) {
      return null;
    }
    let candidate = value.trim();
    if (!candidate) {
      return null;
    }
    if (!/^https?:/i.test(candidate) && !candidate.startsWith("//") && !candidate.startsWith("/")) {
      candidate = `https://${candidate}`;
    }
    try {
      const parsed = new URL(candidate, window.location.origin);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return null;
      }
      return parsed.origin;
    } catch (error) {
      return null;
    }
  }

  function loadTooltipMessages() {
    const script = document.getElementById("slidesEditorTooltips");
    if (!script || !script.textContent) {
      return {};
    }
    try {
      const parsed = JSON.parse(script.textContent);
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch (error) {
      // Ignore malformed tooltip configuration; fall back to defaults.
    }
    return {};
  }

  function getTooltipText(key, fallback) {
    if (!key) {
      return fallback || "";
    }
    const value = tooltipMessages[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
    return fallback || "";
  }

  function applyTooltip(target, key, fallback) {
    if (!target) {
      return;
    }
    const text = getTooltipText(key, fallback);
    if (!text) {
      return;
    }
    target.setAttribute("data-tooltip", text);
    target.setAttribute("aria-label", text);
  }
})();
