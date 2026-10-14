    (() => {
      const stage = document.querySelector('.deck-stage');
      const slides = [...stage.querySelectorAll(':scope > .slide')];
      const chapterNav = document.getElementById('chapterNav');
      const dots = document.getElementById('deckDots');
      const progressBar = document.getElementById('progressBar');
      const overviewGrid = document.getElementById('overviewGrid');
      const overviewOverlay = document.getElementById('overviewOverlay');
      const helpOverlay = document.getElementById('helpOverlay');
      const notesPanel = document.getElementById('notesPanel');
      const controls = document.querySelector('.deck-controls');
      let current = 0;
      let wheelLocked = false;
      let touchStart = null;
      let idleTimer = null;
      let pointerFrame = null;
      let previousFocus = null;
      let printState = null;

      const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
      const slideTitle = (slide) => slide.dataset.slideTitle || slide.dataset.title || slide.querySelector('h1,h2,h3')?.textContent?.trim() || slide.id;
      const isInteractive = (target) => Boolean(target?.closest?.('button, a, input, textarea, select, [contenteditable="true"]'));
      const isTextEntry = (target) => Boolean(target?.closest?.('input, textarea, select, [contenteditable="true"]'));

      function fragmentGroups(slide) {
        const fragments = [...slide.querySelectorAll('[data-fragment]')];
        const groups = new Map();
        fragments.forEach((fragment, index) => {
          const parsed = Number.parseInt(fragment.dataset.fragment, 10);
          const step = Number.isFinite(parsed) && parsed > 0 ? parsed : index + 1;
          if (!groups.has(step)) groups.set(step, []);
          groups.get(step).push(fragment);
        });
        return [...groups.entries()].sort((a, b) => a[0] - b[0]);
      }

      function nextFragment(slide) {
        const group = fragmentGroups(slide).find(([, fragments]) => fragments.some((fragment) => !fragment.classList.contains('is-shown')));
        if (!group) return false;
        group[1].forEach((fragment) => fragment.classList.add('is-shown'));
        return true;
      }

      function previousFragment(slide) {
        const groups = fragmentGroups(slide).filter(([, fragments]) => fragments.some((fragment) => fragment.classList.contains('is-shown')));
        const group = groups.at(-1);
        if (!group) return false;
        group[1].forEach((fragment) => fragment.classList.remove('is-shown'));
        return true;
      }

      function setFragmentState(slide, mode) {
        slide.querySelectorAll('[data-fragment]').forEach((fragment) => fragment.classList.toggle('is-shown', mode === 'all'));
      }

      function updateNotes(slide) {
        const source = slide.querySelector('.speaker-notes');
        notesPanel.querySelector('p').textContent = source?.textContent?.trim() || '';
      }

      function updateChrome(slide) {
        const chapter = slide.dataset.chapter || '';
        chapterNav.querySelectorAll('button').forEach((button) => button.classList.toggle('is-active', button.dataset.chapter === chapter));
        dots.querySelectorAll('button').forEach((button, index) => {
          button.classList.toggle('is-active', index === current);
          button.classList.toggle('is-dark', slide.dataset.tone === 'dark');
          button.setAttribute('aria-current', index === current ? 'true' : 'false');
        });
        overviewGrid.querySelectorAll('button').forEach((button, index) => button.classList.toggle('is-active', index === current));
        progressBar.style.transform = `scaleX(${(current + 1) / slides.length})`;
      }

      function announceSlide(slide) {
        document.dispatchEvent(new CustomEvent('clara:slidechange', {
          detail: {
            slideId: slide.id,
            slideTitle: slideTitle(slide),
            slideIndex: current,
          },
        }));
      }

      function showSlide(index, options = {}) {
        const next = clamp(index, 0, slides.length - 1);
        const direction = next < current ? 'backward' : 'forward';
        current = next;
        slides.forEach((slide, slideIndex) => {
          const active = slideIndex === current;
          slide.classList.toggle('is-active', active);
          slide.classList.toggle('is-before', slideIndex < current);
          slide.classList.toggle('is-after', slideIndex > current);
          slide.setAttribute('aria-hidden', active ? 'false' : 'true');
          slide.toggleAttribute('inert', !active);
          slide.dataset.active = active ? 'true' : 'false';
          if (active && options.resetFragments !== false) {
            setFragmentState(slide, direction === 'backward' ? 'all' : 'none');
          }
        });
        const slide = slides[current];
        updateChrome(slide);
        updateNotes(slide);
        const targetHash = `#${encodeURIComponent(slide.id)}`;
        if (location.hash !== targetHash) history.replaceState(null, '', targetHash);
        announceSlide(slide);
        wakeChrome();
      }

      function advance() {
        if (nextFragment(slides[current])) return;
        if (current < slides.length - 1) showSlide(current + 1);
      }

      function retreat() {
        if (previousFragment(slides[current])) return;
        if (current > 0) showSlide(current - 1);
      }

      function goToHash() {
        const id = decodeURIComponent(location.hash.slice(1));
        const index = slides.findIndex((slide) => slide.id === id);
        if (index >= 0 && index !== current) showSlide(index);
      }

      function buildChrome() {
        const chapters = [];
        slides.forEach((slide, index) => {
          const title = slideTitle(slide);
          const chapter = slide.dataset.chapter || `chapter-${index + 1}`;
          const label = slide.dataset.chapterLabel || chapter.replace(/[-_]+/g, ' ');
          if (!chapters.some((item) => item.id === chapter)) chapters.push({ id: chapter, label, target: slide.id });

          const dot = document.createElement('button');
          dot.type = 'button';
          dot.setAttribute('aria-label', `Go to ${title}`);
          dot.addEventListener('click', () => showSlide(index));
          dots.appendChild(dot);

          const card = document.createElement('button');
          card.type = 'button';
          card.className = 'overview-card';
          card.innerHTML = `<span>${label}</span><strong>${title}</strong>`;
          card.addEventListener('click', () => {
            closeOverlays();
            showSlide(index);
          });
          overviewGrid.appendChild(card);
        });

        chapters.forEach((chapter) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.dataset.chapter = chapter.id;
          button.textContent = chapter.label;
          button.addEventListener('click', () => {
            const index = slides.findIndex((slide) => slide.id === chapter.target);
            if (index >= 0) showSlide(index);
          });
          chapterNav.appendChild(button);
        });
      }

      function focusableWithin(container) {
        return [...container.querySelectorAll('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter((element) => !element.disabled && element.offsetParent !== null);
      }

      function openOverlay(overlay) {
        closeOverlays(false);
        previousFocus = document.activeElement;
        overlay.hidden = false;
        document.body.classList.remove('show-notes');
        requestAnimationFrame(() => focusableWithin(overlay)[0]?.focus());
      }

      function closeOverlays(restoreFocus = true) {
        [overviewOverlay, helpOverlay].forEach((overlay) => { overlay.hidden = true; });
        if (restoreFocus && previousFocus instanceof HTMLElement) previousFocus.focus();
        previousFocus = null;
      }

      function trapOverlayFocus(event) {
        const overlay = [overviewOverlay, helpOverlay].find((candidate) => !candidate.hidden);
        if (!overlay || event.key !== 'Tab') return;
        const items = focusableWithin(overlay);
        if (!items.length) return;
        const first = items[0];
        const last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }

      async function toggleFullscreen() {
        if (!document.fullscreenElement) await document.documentElement.requestFullscreen?.();
        else await document.exitFullscreen?.();
      }

      function wakeChrome() {
        document.body.classList.remove('ui-idle');
        window.clearTimeout(idleTimer);
        idleTimer = window.setTimeout(() => {
          if (!document.body.classList.contains('show-notes') && overviewOverlay.hidden && helpOverlay.hidden) document.body.classList.add('ui-idle');
        }, 2600);
      }

      function updateSpotlight(event) {
        if (window.matchMedia('(pointer: coarse), (prefers-reduced-motion: reduce)').matches) return;
        if (pointerFrame) return;
        pointerFrame = requestAnimationFrame(() => {
          const rect = stage.getBoundingClientRect();
          const x = clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100);
          const y = clamp(((event.clientY - rect.top) / rect.height) * 100, 0, 100);
          document.documentElement.style.setProperty('--mx', `${x}%`);
          document.documentElement.style.setProperty('--my', `${y}%`);
          pointerFrame = null;
        });
      }

      function handleKey(event) {
        trapOverlayFocus(event);
        if (event.defaultPrevented || isTextEntry(event.target)) return;
        const key = event.key.toLowerCase();
        if (isInteractive(event.target) && (key === ' ' || key === 'enter')) return;
        if (['arrowright', 'arrowdown', 'pagedown', ' '].includes(key)) { event.preventDefault(); advance(); }
        else if (['arrowleft', 'arrowup', 'pageup'].includes(key)) { event.preventDefault(); retreat(); }
        else if (key === 'home') { event.preventDefault(); showSlide(0); }
        else if (key === 'end') { event.preventDefault(); showSlide(slides.length - 1); }
        else if (key === 'o') openOverlay(overviewOverlay);
        else if (key === 'n') { document.body.classList.toggle('show-notes'); closeOverlays(false); wakeChrome(); }
        else if (key === 'f') toggleFullscreen();
        else if (key === 'h' || key === '?') openOverlay(helpOverlay);
        else if (key === 'escape') { closeOverlays(); document.body.classList.remove('show-notes'); }
      }

      function beforePrint() {
        printState = slides.map((slide) => [...slide.querySelectorAll('[data-fragment]')].map((fragment) => fragment.classList.contains('is-shown')));
        slides.forEach((slide) => setFragmentState(slide, 'all'));
      }

      function afterPrint() {
        if (!printState) return;
        slides.forEach((slide, slideIndex) => {
          slide.querySelectorAll('[data-fragment]').forEach((fragment, fragmentIndex) => fragment.classList.toggle('is-shown', Boolean(printState[slideIndex]?.[fragmentIndex])));
        });
        printState = null;
      }

      buildChrome();
      const hashIndex = slides.findIndex((slide) => slide.id === decodeURIComponent(location.hash.slice(1)));
      current = hashIndex >= 0 ? hashIndex : Math.max(0, slides.findIndex((slide) => slide.classList.contains('is-active') || slide.getAttribute('aria-hidden') === 'false'));
      showSlide(current, { resetFragments: false });

      document.getElementById('prevBtn').addEventListener('click', retreat);
      document.getElementById('nextBtn').addEventListener('click', advance);
      document.getElementById('overviewBtn').addEventListener('click', () => openOverlay(overviewOverlay));
      document.getElementById('helpBtn').addEventListener('click', () => openOverlay(helpOverlay));
      document.getElementById('fullscreenBtn').addEventListener('click', toggleFullscreen);
      document.querySelectorAll('[data-close-overlay]').forEach((button) => button.addEventListener('click', closeOverlays));
      [overviewOverlay, helpOverlay].forEach((overlay) => overlay.addEventListener('pointerdown', (event) => { if (event.target === overlay) closeOverlays(); }));

      document.addEventListener('keydown', handleKey);
      window.addEventListener('hashchange', goToHash);
      window.addEventListener('beforeprint', beforePrint);
      window.addEventListener('afterprint', afterPrint);
      document.addEventListener('pointermove', (event) => { wakeChrome(); updateSpotlight(event); }, { passive: true });
      document.addEventListener('touchstart', (event) => {
        wakeChrome();
        if (isInteractive(event.target) || event.touches.length !== 1) return;
        touchStart = { x: event.touches[0].clientX, y: event.touches[0].clientY };
      }, { passive: true });
      document.addEventListener('touchend', (event) => {
        if (!touchStart || !event.changedTouches.length) return;
        const dx = event.changedTouches[0].clientX - touchStart.x;
        const dy = event.changedTouches[0].clientY - touchStart.y;
        touchStart = null;
        if (Math.abs(dx) > 54 && Math.abs(dx) > Math.abs(dy) * 1.35) (dx < 0 ? advance : retreat)();
      }, { passive: true });
      document.addEventListener('wheel', (event) => {
        if (wheelLocked || isInteractive(event.target) || Math.abs(event.deltaY) < 18) return;
        wheelLocked = true;
        (event.deltaY > 0 ? advance : retreat)();
        window.setTimeout(() => { wheelLocked = false; }, 520);
      }, { passive: true });

      controls.addEventListener('pointerenter', wakeChrome);
      wakeChrome();
    })();
