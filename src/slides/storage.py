from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from bs4 import BeautifulSoup  # type: ignore[import]

from src.file_lock import FileLock

from .errors import DeckNotFoundError, SlideNotFoundError
from .html_normalizer import update_slide_document
from .loader import (
    INDEX_HTML,
    INDEX_JSON,
    is_index_filename,
    iter_deck_ids,
    load_deck,
    load_slide,
)
from .models import Deck, Slide
from .notebooklm_style import build_notebooklm_css_variables, load_notebooklm_style
from .service import generate_slide_filename

__all__ = ["DeckStorage", "render_slide_html", "write_index_html"]

_SLIDE_SUFFIXES = {".html", ".htm"}
_OCR_JSON = "ocr.json"
_LAYOUT_JSON = "layout.json"
_SLIDE_ANALYSIS_JSON = "slide_analysis.json"
_ASSET_URL_PATTERN = re.compile(r"url\(([^)]+)\)")

LOGGER = logging.getLogger(__name__)


INDEX_VIEWER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__DECK_NAME__</title>
    <style>
        :root {
            --text-color: #111111;
            --secondary-text: #666666;
            --bg-color: #ffffff;
            --light-bg: #f8f8f8;
            --dark-bg: #111111;
            --border-color: #e0e0e0;
            --hover-color: #f0f0f0;
            --active-color: #000000;
            --shadow: 0 1px 2px rgba(0, 0, 0, 0.05), 0 1px 4px rgba(0, 0, 0, 0.05), 0 2px 8px rgba(0, 0, 0, 0.05);
            --btn-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
            --card-radius: 4px;
            --btn-radius: 4px;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }
        
        body {
            background-color: var(--light-bg);
            color: var(--text-color);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }
        
        .container {
            max-width: 1800px;
            margin: 0 auto;
            padding: 24px;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            background-color: var(--dark-bg);
            color: white;
            margin-bottom: 32px;
            box-shadow: var(--shadow);
        }
        
        header h1 {
            font-size: 18px;
            font-weight: 500;
            letter-spacing: 0.2px;
            display: flex;
            align-items: center;
        }
        
        header h1 svg {
            margin-right: 12px;
        }
        
        .controls {
            display: flex;
            gap: 16px;
            align-items: center;
        }
        
        .view-controls {
            display: flex;
            background: rgba(255, 255, 255, 0.1);
            border-radius: var(--btn-radius);
            overflow: hidden;
        }
        
        .view-controls button {
            background: none;
            color: white;
            border: none;
            padding: 6px 12px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.2s ease;
        }
        
        .view-controls button.active {
            background: rgba(255, 255, 255, 0.2);
        }
        
        .play-button {
            background-color: white;
            color: var(--dark-bg);
            border: none;
            padding: 8px 16px;
            border-radius: var(--btn-radius);
            cursor: pointer;
            display: flex;
            align-items: center;
            transition: all 0.2s ease;
            font-weight: 500;
            font-size: 13px;
            box-shadow: var(--btn-shadow);
        }
        
        .play-button:hover {
            background-color: var(--hover-color);
            transform: translateY(-1px);
        }
        
        .play-button svg {
            margin-right: 8px;
        }
        
        /* Grid View */
        .preview-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(480px, 1fr));
            gap: 24px;
            margin-top: 24px;
        }
        
        /* Grid mode specific styles */
        .preview-container:not(.list-view) .slide-frame-container {
            position: relative;
            padding-top: 56.25%; /* 16:9 Aspect Ratio */
            width: 100%;
            overflow: hidden;
        }
        
        .preview-container:not(.list-view) .slide-frame {
            position: absolute;
            top: 50%;
            left: 50%;
            width: 1280px;
            height: 720px;
            border: none;
            transform-origin: center center;
            transform: translate(-50%, -50%) scale(1);
        }
        
        /* List View */
        .preview-container.list-view {
            display: flex;
            flex-direction: column;
            gap: 32px;
            align-items: center;
        }
        
        .preview-container.list-view .slide-preview {
            width: 90vw;
            max-width: 1280px;
            height: auto;
            aspect-ratio: 16 / 9;
        }

        .preview-container.list-view .slide-frame-container {
            width: 100%;
            height: 100%;
            position: relative;
            overflow: hidden;
        }

        .preview-container.list-view .slide-frame {
            position: absolute;
            top: 50%;
            left: 50%;
            width: 1280px;
            height: 720px;
            border: none;
            transform: translate(-50%, -50%);
            transform-origin: center center;
        }
        
        .slide-preview {
            background: var(--bg-color);
            border-radius: var(--card-radius);
            overflow: hidden;
            box-shadow: var(--shadow);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            cursor: pointer;
            position: relative;
            border: 1px solid var(--border-color);
        }
        
        .slide-preview:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.08);
        }
        
        .slide-preview.active {
            border: 1px solid var(--active-color);
        }
        
        .slide-number {
            position: absolute;
            top: 12px;
            left: 12px;
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 600;
            z-index: 2;
        }
        
        /* Presentation mode */
        .presentation-mode {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: #000;
            z-index: 1000;
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        
        /* Fullscreen mode adjustments */
        .presentation-mode:fullscreen {
            width: 100vw;
            height: 100vh;
        }
        
        .presentation-mode:-webkit-full-screen {
            width: 100vw;
            height: 100vh;
        }
        
        .presentation-mode:-moz-full-screen {
            width: 100vw;
            height: 100vh;
        }
        
        .presentation-mode:-ms-fullscreen {
            width: 100vw;
            height: 100vh;
        }
        
        .presentation-slide {
            width: 1280px;
            height: 720px;
            border: none;
            transform-origin: center center;
        }
        
        .presentation-slide-container {
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 1;
            width: 100%;
            padding: 20px;
        }
        
        .presentation-controls {
            height: 48px;
            background-color: rgba(0, 0, 0, 0.9);
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 24px;
            padding: 0 24px;
            position: relative;
            z-index: 1001;
        }
        
        .presentation-controls.fullscreen {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .presentation-controls.fullscreen:hover,
        .presentation-controls.fullscreen.show {
            opacity: 1;
        }
        
        .progress-bar {
            flex: 1;
            max-width: 400px;
            height: 2px;
            background-color: rgba(255, 255, 255, 0.2);
            border-radius: 1px;
            overflow: hidden;
            position: relative;
        }
        
        .progress-fill {
            height: 100%;
            background-color: white;
            width: 0%;
            transition: width 0.3s ease;
        }
        
        .slide-indicators {
            color: white;
            font-size: 12px;
            min-width: 40px;
            text-align: center;
        }
        
        .presentation-controls button {
            background-color: transparent;
            color: white;
            border: none;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background-color 0.2s ease;
        }
        
        .presentation-controls button:hover {
            background-color: rgba(255, 255, 255, 0.1);
        }
        
        /* Responsive adjustments */
        @media (max-width: 1200px) {
            .preview-container:not(.list-view) {
                grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            }
        }
        
        @media (max-width: 900px) {
            .preview-container:not(.list-view) {
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            }
        }
        
        @media (max-width: 640px) {
            .container {
                padding: 16px;
            }
            
            .preview-container:not(.list-view) {
                grid-template-columns: 1fr;
                gap: 16px;
            }
            
            header {
                flex-direction: column;
                align-items: flex-start;
                gap: 16px;
                padding: 16px;
            }
            
            .controls {
                width: 100%;
                justify-content: space-between;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>
                __DECK_NAME__
            </h1>
            <div class="controls">
                <div class="view-controls">
                    <button id="grid-view-btn">Grid</button>
                    <button id="list-view-btn" class="active">List</button>
                </div>
                <button id="play-button" class="play-button">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                    Play Slides
                </button>
            </div>
        </header>
        
        <div class="preview-container list-view" id="preview-container">
            <!-- Slide previews will be dynamically inserted here -->
        </div>
    </div>
    
    <div class="presentation-mode" id="presentation-mode">
        <div class="presentation-slide-container">
            <iframe id="presentation-slide" class="presentation-slide" src="" frameborder="0"></iframe>
        </div>
        <div class="presentation-controls">
            <button id="prev-slide">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="19" y1="12" x2="5" y2="12"></line>
                    <polyline points="12 19 5 12 12 5"></polyline>
                </svg>
            </button>
            <div class="progress-bar">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
            <div class="slide-indicators">
                <span id="current-slide">1</span>/<span id="total-slides">0</span>
            </div>
            <button id="next-slide">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                    <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
            </button>
            <button id="fullscreen-toggle" title="Toggle Fullscreen">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                </svg>
            </button>
            <button id="exit-presentation">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    <line x1="9" y1="9" x2="15" y2="15"></line>
                    <line x1="15" y1="9" x2="9" y2="15"></line>
                </svg>
            </button>
        </div>
    </div>

    <script>
        // Load the slides data
        const slides = __SLIDES_ARRAY__;
        let currentSlideIndex = 0;
        let viewMode = 'list'; // 'grid' or 'list'
        
        // DOM elements
        const previewContainer = document.getElementById('preview-container');
        const presentationMode = document.getElementById('presentation-mode');
        const presentationSlide = document.getElementById('presentation-slide');
        const playButton = document.getElementById('play-button');
        const prevButton = document.getElementById('prev-slide');
        const nextButton = document.getElementById('next-slide');
        const exitButton = document.getElementById('exit-presentation');
        const fullscreenToggle = document.getElementById('fullscreen-toggle');
        const presentationControls = document.querySelector('.presentation-controls');
        const progressFill = document.getElementById('progress-fill');
        const currentSlideElement = document.getElementById('current-slide');
        const totalSlidesElement = document.getElementById('total-slides');
        const gridViewBtn = document.getElementById('grid-view-btn');
        const listViewBtn = document.getElementById('list-view-btn');
        
        // Fullscreen state
        let isFullscreen = false;
        let controlsTimeout;
        
        // Initialize the viewer
        function initViewer() {
            // Set total slides
            totalSlidesElement.textContent = slides.length;
            
            // Generate slide previews
            generatePreviews();
            
            // Set up view mode buttons
            gridViewBtn.addEventListener('click', () => setViewMode('grid'));
            listViewBtn.addEventListener('click', () => setViewMode('list'));
        }
        
        // Generate slide previews
        function generatePreviews() {
            previewContainer.innerHTML = '';

            let loadedCount = 0;
            const totalSlides = slides.length;

            slides.forEach((slide, index) => {
                const slidePreview = document.createElement('div');
                slidePreview.className = 'slide-preview';
                if (index === currentSlideIndex) {
                    slidePreview.classList.add('active');
                }

                slidePreview.innerHTML = `
                    <div class="slide-number">${index + 1}</div>
                    <div class="slide-frame-container">
                        <iframe class="slide-frame" src="${slide}" frameborder="0"></iframe>
                    </div>
                `;

                slidePreview.addEventListener('click', () => {
                    startPresentation(index);
                });

                // Wait for iframe to load before scaling
                const iframe = slidePreview.querySelector('.slide-frame');
                iframe.addEventListener('load', () => {
                    loadedCount++;
                    // When all iframes are loaded, scale them
                    if (loadedCount === totalSlides) {
                        if (viewMode === 'grid') {
                            setTimeout(scaleGridPreviews, 100);
                        } else if (viewMode === 'list') {
                            setTimeout(scaleListPreviews, 100);
                        }
                    }
                });

                previewContainer.appendChild(slidePreview);
            });
        }
        
        // Set view mode (grid or list)
        function setViewMode(mode) {
            viewMode = mode;

            if (mode === 'grid') {
                previewContainer.classList.remove('list-view');
                gridViewBtn.classList.add('active');
                listViewBtn.classList.remove('active');

                // Scale grid previews after mode change
                setTimeout(scaleGridPreviews, 100);
            } else {
                previewContainer.classList.add('list-view');
                gridViewBtn.classList.remove('active');
                listViewBtn.classList.add('active');

                // Scale list previews after mode change
                setTimeout(scaleListPreviews, 100);
            }
        }

        // Scale list mode previews
        function scaleListPreviews() {
            if (viewMode !== 'list') return;

            const slidePreviews = document.querySelectorAll('.preview-container.list-view .slide-preview');
            slidePreviews.forEach(preview => {
                const frame = preview.querySelector('.slide-frame');
                if (!frame) return;

                // Get the container dimensions
                const container = frame.closest('.slide-frame-container');
                const containerWidth = container.clientWidth;
                const containerHeight = container.clientHeight;

                // Calculate scale to fit 1280x720 within container
                const scaleX = containerWidth / 1280;
                const scaleY = containerHeight / 720;
                const scale = Math.min(scaleX, scaleY);

                // Apply both translate (center) and scale
                frame.style.transform = `translate(-50%, -50%) scale(${scale})`;
            });
        }
        
        // Scale grid mode previews
        function scaleGridPreviews() {
            if (viewMode !== 'grid') return;
            
            const slideFrames = document.querySelectorAll('.preview-container:not(.list-view) .slide-frame');
            slideFrames.forEach(frame => {
                const container = frame.closest('.slide-frame-container');
                if (!container) return;
                
                const containerWidth = container.clientWidth;
                const containerHeight = container.clientHeight;

                // Calculate scale to fit 1280x720 within container
                const scaleX = containerWidth / 1280;
                const scaleY = containerHeight / 720;
                const scale = Math.min(scaleX, scaleY);
                
                frame.style.transform = `translate(-50%, -50%) scale(${scale})`;
            });
        }
        
        // Start presentation mode
        function startPresentation(index = 0) {
            currentSlideIndex = index;
            presentationMode.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            updateSlide();
            
            // Auto-enter fullscreen
            requestFullscreen();
        }
        
        // Request fullscreen
        function requestFullscreen() {
            const element = presentationMode;
            
            if (element.requestFullscreen) {
                element.requestFullscreen();
            } else if (element.webkitRequestFullscreen) {
                element.webkitRequestFullscreen();
            } else if (element.mozRequestFullScreen) {
                element.mozRequestFullScreen();
            } else if (element.msRequestFullscreen) {
                element.msRequestFullscreen();
            }
        }
        
        // Exit fullscreen
        function exitFullscreen() {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        }
        
        // Toggle fullscreen
        function toggleFullscreen() {
            if (isFullscreen) {
                exitFullscreen();
            } else {
                requestFullscreen();
            }
        }
        
        // Handle fullscreen change
        function handleFullscreenChange() {
            isFullscreen = !!(document.fullscreenElement || 
                            document.webkitFullscreenElement || 
                            document.mozFullScreenElement || 
                            document.msFullscreenElement);
            
            if (isFullscreen) {
                presentationControls.classList.add('fullscreen');
                setupControlsAutoHide();
            } else {
                presentationControls.classList.remove('fullscreen');
                clearTimeout(controlsTimeout);
            }
            
            // Re-scale slide when fullscreen changes
            setTimeout(scalePresentationSlide, 100);
        }
        
        // Setup auto-hide controls in fullscreen
        function setupControlsAutoHide() {
            if (!isFullscreen) return;
            
            // Show controls initially
            presentationControls.classList.add('show');
            
            // Auto-hide after 3 seconds
            controlsTimeout = setTimeout(() => {
                if (isFullscreen) {
                    presentationControls.classList.remove('show');
                }
            }, 3000);
        }
        
        // Show controls temporarily
        function showControlsTemporarily() {
            if (!isFullscreen) return;
            
            presentationControls.classList.add('show');
            clearTimeout(controlsTimeout);
            
            controlsTimeout = setTimeout(() => {
                if (isFullscreen) {
                    presentationControls.classList.remove('show');
                }
            }, 3000);
        }
        
        // Exit presentation mode
        function exitPresentation() {
            // Exit fullscreen if in fullscreen mode
            if (isFullscreen) {
                exitFullscreen();
            }
            
            presentationMode.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
        
        // Update current slide
        function updateSlide() {
            presentationSlide.src = slides[currentSlideIndex];
            currentSlideElement.textContent = currentSlideIndex + 1;
            
            // Update progress bar
            const progress = ((currentSlideIndex + 1) / slides.length) * 100;
            progressFill.style.width = `${progress}%`;
            
            // Scale presentation slide to fit container
            scalePresentationSlide();
            
            // Update preview highlighting
            document.querySelectorAll('.slide-preview').forEach((preview, index) => {
                if (index === currentSlideIndex) {
                    preview.classList.add('active');
                } else {
                    preview.classList.remove('active');
                }
            });
        }
        
        // Scale presentation slide to fit container
        function scalePresentationSlide() {
            const container = document.querySelector('.presentation-slide-container');
            const containerWidth = container.clientWidth - 40; // Account for padding
            const containerHeight = container.clientHeight - 40;
            
            // In fullscreen mode, use full viewport dimensions
            if (isFullscreen) {
                const viewportWidth = window.innerWidth;
                const viewportHeight = window.innerHeight - 48; // Account for controls height

                const scaleX = viewportWidth / 1280;
                const scaleY = viewportHeight / 720;
                const scale = Math.min(scaleX, scaleY);

                presentationSlide.style.transform = `scale(${scale})`;
            } else {
                // Calculate scale based on container size and slide dimensions (1280x720)
                const scaleX = containerWidth / 1280;
                const scaleY = containerHeight / 720;
                const scale = Math.min(scaleX, scaleY);

                presentationSlide.style.transform = `scale(${scale})`;
            }
        }
        
        // Go to next slide
        function nextSlide() {
            if (currentSlideIndex < slides.length - 1) {
                currentSlideIndex++;
                updateSlide();
            }
        }
        
        // Go to previous slide
        function prevSlide() {
            if (currentSlideIndex > 0) {
                currentSlideIndex--;
                updateSlide();
            }
        }
        
        // Event listeners
        playButton.addEventListener('click', () => startPresentation(0));
        prevButton.addEventListener('click', () => {
            prevSlide();
            showControlsTemporarily();
        });
        nextButton.addEventListener('click', () => {
            nextSlide();
            showControlsTemporarily();
        });
        exitButton.addEventListener('click', exitPresentation);
        fullscreenToggle.addEventListener('click', () => {
            toggleFullscreen();
            showControlsTemporarily();
        });
        
        // Fullscreen change listeners
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('MSFullscreenChange', handleFullscreenChange);
        
        // Mouse movement in fullscreen mode
        presentationMode.addEventListener('mousemove', showControlsTemporarily);
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (presentationMode.style.display === 'flex') {
                if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'n') {
                    nextSlide();
                    showControlsTemporarily();
                } else if (e.key === 'ArrowLeft' || e.key === 'p') {
                    prevSlide();
                    showControlsTemporarily();
                } else if (e.key === 'Escape') {
                    if (isFullscreen) {
                        exitFullscreen();
                    } else {
                        exitPresentation();
                    }
                } else if (e.key === 'f' || e.key === 'F') {
                    toggleFullscreen();
                    showControlsTemporarily();
                }
            }
        });
        
        // Initialize the viewer when the page loads
        window.addEventListener('load', initViewer);
        
        // Handle window resize for presentation mode scaling
        window.addEventListener('resize', () => {
            if (presentationMode.style.display === 'flex') {
                scalePresentationSlide();
            }

            // Scale previews on resize
            if (viewMode === 'grid') {
                scaleGridPreviews();
            } else if (viewMode === 'list') {
                scaleListPreviews();
            }
        });
    </script>
</body>
</html>

"""


def _load_json_payload(path: Path, *, payload_name: str) -> dict[str, object] | None:
    if not path.exists():
        return None
    with FileLock(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            LOGGER.warning(
                "Ignoring unreadable %s payload at %s: %s", payload_name, path, exc
            )
            return None


class DeckStorage:
    """Filesystem-backed repository for HTML slide decks."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def list_decks(self) -> list[str]:
        """Return the sorted list of deck identifiers."""

        return list(iter_deck_ids(self._root))

    def load_deck(self, deck_id: str) -> Deck:
        """Load ``deck_id`` raising :class:`DeckNotFoundError` when missing."""

        return load_deck(deck_id, self._root)

    def list_slide_ids(self, deck_id: str) -> list[str]:
        """Return slide filenames currently stored on disk."""

        deck_path = self._root / deck_id
        if not deck_path.exists():
            return []
        entries: list[str] = []
        for entry in sorted(deck_path.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in _SLIDE_SUFFIXES:
                continue
            if is_index_filename(entry.name):
                continue
            entries.append(entry.name)
        return entries

    def save_deck(self, deck: Deck) -> None:
        """Persist ``deck`` to disk."""

        deck_path = self._root / deck.deck_id
        lock_target = deck_path / INDEX_HTML
        with FileLock(lock_target):
            deck_path.mkdir(parents=True, exist_ok=True)
            deck.sync_section_headers()
            desired = set(deck.slide_ids())
            _write_slides(deck_path, deck)
            _remove_stale_slides(deck_path, desired)
            write_index_html(deck_path, deck.slides)
            _write_index_json(deck_path, deck)
            _prune_deck_ocr_payloads(deck, deck_path)
            _prune_deck_layout_payloads(deck, deck_path)
            _prune_deck_slide_analysis_payloads(deck, deck_path)

    def load_ocr_payload(self, deck_id: str) -> dict[str, object] | None:
        """Return the stored OCR payload for ``deck_id`` when available."""

        deck_path = self._root / deck_id
        ocr_path = deck_path / _OCR_JSON
        return _load_json_payload(ocr_path, payload_name="OCR")

    def save_ocr_payload(self, deck_id: str, payload: dict[str, object]) -> None:
        """Persist OCR payload data for ``deck_id``."""

        deck_path = self._root / deck_id
        if not deck_path.exists():
            raise DeckNotFoundError(f"Deck {deck_id} not found under {self._root}")
        ocr_path = deck_path / _OCR_JSON
        with FileLock(ocr_path):
            ocr_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def load_layout_payload(self, deck_id: str) -> dict[str, object] | None:
        """Return the stored layout payload for ``deck_id`` when available."""

        deck_path = self._root / deck_id
        layout_path = deck_path / _LAYOUT_JSON
        return _load_json_payload(layout_path, payload_name="layout")

    def save_layout_payload(self, deck_id: str, payload: dict[str, object]) -> None:
        """Persist layout payload data for ``deck_id``."""

        deck_path = self._root / deck_id
        if not deck_path.exists():
            raise DeckNotFoundError(f"Deck {deck_id} not found under {self._root}")
        layout_path = deck_path / _LAYOUT_JSON
        with FileLock(layout_path):
            layout_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def load_slide_analysis_payload(self, deck_id: str) -> dict[str, object] | None:
        """Return the stored merged slide-analysis payload for ``deck_id`` when available."""

        deck_path = self._root / deck_id
        analysis_path = deck_path / _SLIDE_ANALYSIS_JSON
        return _load_json_payload(analysis_path, payload_name="slide analysis")

    def save_slide_analysis_payload(
        self, deck_id: str, payload: dict[str, object]
    ) -> None:
        """Persist merged slide-analysis payload data for ``deck_id``."""

        deck_path = self._root / deck_id
        if not deck_path.exists():
            raise DeckNotFoundError(f"Deck {deck_id} not found under {self._root}")
        analysis_path = deck_path / _SLIDE_ANALYSIS_JSON
        with FileLock(analysis_path):
            analysis_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def archive_deck(self, deck_id: str) -> bool:
        """Move ``deck_id`` into the hidden archive folder when it exists."""

        deck_path = self._root / deck_id
        if not deck_path.exists():
            return False
        archive_root = self._root / ".trash"
        archive_root.mkdir(parents=True, exist_ok=True)
        target_path = archive_root / deck_id
        if target_path.exists():
            raise DeckNotFoundError(f"Archive already contains deck {deck_id}")
        deck_path.replace(target_path)
        return True

    def restore_deck(self, deck_id: str) -> bool:
        """Restore ``deck_id`` from the hidden archive folder when available."""

        archive_root = self._root / ".trash"
        archive_path = archive_root / deck_id
        if not archive_path.exists():
            return False
        target_path = self._root / deck_id
        if target_path.exists():
            raise DeckNotFoundError(f"Deck {deck_id} already exists under {self._root}")
        archive_path.replace(target_path)
        return True

    def import_slide(
        self,
        source_deck_id: str,
        source_slide_id: str,
        target_deck_id: str,
        *,
        new_slide_id: str | None = None,
    ) -> Slide:
        """Copy a slide from ``source`` into ``target`` returning the new :class:`Slide`."""

        source_path = self._root / source_deck_id
        target_path = self._root / target_deck_id
        if not source_path.exists():
            raise DeckNotFoundError(
                f"Deck {source_deck_id} not found under {self._root}"
            )
        target_path.mkdir(parents=True, exist_ok=True)
        slide_id = new_slide_id or generate_slide_filename(
            _existing_slide_ids(target_path)
        )
        src_file = source_path / source_slide_id
        dest_file = target_path / slide_id
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if not src_file.exists():
            raise SlideNotFoundError(
                f"Slide {source_slide_id} not found in {source_deck_id}"
            )
        try:
            shutil.copy2(src_file, dest_file)
        except FileNotFoundError as exc:
            raise SlideNotFoundError(
                f"Slide {source_slide_id} not found in {source_deck_id}"
            ) from exc
        asset_paths: set[str] = set()
        try:
            original_html = dest_file.read_text(encoding="utf-8")
            rewritten_html, asset_paths = _rewrite_imported_slide_assets(
                original_html,
                source_deck_id=source_deck_id,
                target_deck_id=target_deck_id,
            )
            if rewritten_html != original_html:
                dest_file.write_text(rewritten_html, encoding="utf-8")
        except OSError as exc:
            LOGGER.warning(
                "Failed to rewrite assets for imported slide %s: %s", dest_file, exc
            )
        if asset_paths:
            _copy_imported_assets(
                source_path=source_path,
                target_path=target_path,
                asset_paths=asset_paths,
            )
        slide = load_slide(target_path, slide_id)
        slide.kind = "normal"
        slide.section_id = None
        slide.subsection_id = None
        return slide


def _existing_slide_ids(deck_path: Path) -> Iterable[str]:
    for entry in deck_path.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in _SLIDE_SUFFIXES:
            continue
        if is_index_filename(entry.name):
            continue
        yield entry.name


def _write_slides(deck_path: Path, deck: Deck) -> None:
    for slide in deck.slides:
        html_text = render_slide_html(slide)
        (deck_path / slide.id).write_text(html_text, encoding="utf-8")
    _write_section_styles(deck_path, deck)


def _remove_stale_slides(deck_path: Path, expected: set[str]) -> None:
    for entry in deck_path.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in _SLIDE_SUFFIXES:
            continue
        if is_index_filename(entry.name):
            continue
        if entry.name in expected:
            continue
        entry.unlink(missing_ok=True)


def _prune_deck_ocr_payloads(deck: Deck, deck_path: Path) -> None:
    deck_slide_ids = deck.slide_ids()
    _prune_payload_file(deck_path / _OCR_JSON, deck_slide_ids)


def _prune_deck_layout_payloads(deck: Deck, deck_path: Path) -> None:
    deck_slide_ids = deck.slide_ids()
    _prune_payload_file(deck_path / _LAYOUT_JSON, deck_slide_ids)


def _prune_deck_slide_analysis_payloads(deck: Deck, deck_path: Path) -> None:
    deck_slide_ids = deck.slide_ids()
    _prune_payload_file(deck_path / _SLIDE_ANALYSIS_JSON, deck_slide_ids)


def _prune_payload_file(payload_path: Path, deck_slide_ids: list[str]) -> None:
    if not payload_path.exists():
        return
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning(
            "Skipping OCR payload pruning; invalid JSON at %s.", payload_path
        )
        return
    if not isinstance(payload, dict):
        LOGGER.warning(
            "Skipping OCR payload pruning; expected JSON object at %s.", payload_path
        )
        return
    pruned_payload, changed = _prune_payload_slides(payload, deck_slide_ids)
    if not changed:
        return
    with FileLock(payload_path):
        payload_path.write_text(
            json.dumps(pruned_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _prune_payload_slides(
    payload: dict[str, object],
    deck_slide_ids: list[str],
) -> tuple[dict[str, object], bool]:
    raw_slides = (
        payload.get("slides") if isinstance(payload.get("slides"), list) else []
    )
    slide_map: dict[str, dict[str, object]] = {}
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            continue
        slide_id = _resolve_payload_slide_id(raw_slide)
        if slide_id and slide_id not in slide_map:
            slide_map[slide_id] = raw_slide
    pruned_slides: list[dict[str, object]] = []
    for index, slide_id in enumerate(deck_slide_ids):
        existing = slide_map.get(slide_id)
        if not existing:
            continue
        updated = {**existing}
        if "slide_number" in existing or "slideNumber" not in existing:
            updated["slide_number"] = index + 1
        if "slideNumber" in existing:
            updated["slideNumber"] = index + 1
        if "page_number" in existing or "pageNumber" not in existing:
            updated["page_number"] = index + 1
        if "pageNumber" in existing:
            updated["pageNumber"] = index + 1
        pruned_slides.append(updated)
    changed = raw_slides != pruned_slides
    if not changed:
        return payload, False
    return {**payload, "slides": pruned_slides}, True


def _resolve_payload_slide_id(slide_payload: dict[str, object]) -> str:
    slide_id = slide_payload.get("slide_id") or slide_payload.get("slideId") or ""
    return str(slide_id).strip()


def _extract_relative_asset_path(
    parsed_url: ParseResult, *, source_deck_id: str
) -> str | None:
    if parsed_url.scheme or parsed_url.netloc:
        return None
    source_prefix = f"/slides/deck/{source_deck_id}/assets/"
    path = parsed_url.path
    if path.startswith(source_prefix):
        return path[len(source_prefix) :]
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("/"):
        path = path[1:]
    if not path.startswith("assets/"):
        return None
    return path[len("assets/") :]


def _rewrite_css_urls(
    style_value: str,
    *,
    source_deck_id: str,
    target_deck_id: str,
    asset_paths: set[str],
) -> str:
    def _replace(match: re.Match[str]) -> str:
        raw_url = match.group(1).strip().strip("'\"")
        replacement = _rewrite_asset_url(
            raw_url,
            source_deck_id=source_deck_id,
            target_deck_id=target_deck_id,
            asset_paths=asset_paths,
        )
        if not replacement:
            return match.group(0)
        return f'url("{replacement}")'

    return _ASSET_URL_PATTERN.sub(_replace, style_value)


def _rewrite_asset_url(
    raw_url: str,
    *,
    source_deck_id: str,
    target_deck_id: str,
    asset_paths: set[str],
) -> str | None:
    parsed = urlparse(raw_url)
    relative_path = _extract_relative_asset_path(parsed, source_deck_id=source_deck_id)
    if not relative_path:
        return None
    asset_paths.add(relative_path)
    suffix = ""
    if parsed.query:
        suffix = f"?{parsed.query}"
    if parsed.fragment:
        suffix = f"{suffix}#{parsed.fragment}"
    return f"/slides/deck/{target_deck_id}/assets/{relative_path}{suffix}"


def _rewrite_imported_slide_assets(
    html: str,
    *,
    source_deck_id: str,
    target_deck_id: str,
) -> tuple[str, set[str]]:
    if not html:
        return html, set()
    soup = BeautifulSoup(html, "html.parser")
    asset_paths: set[str] = set()
    for tag in soup.find_all(True):
        for attr in ("src", "data-src", "href", "poster"):
            value = tag.get(attr)
            if not value:
                continue
            replacement = _rewrite_asset_url(
                value,
                source_deck_id=source_deck_id,
                target_deck_id=target_deck_id,
                asset_paths=asset_paths,
            )
            if replacement:
                tag[attr] = replacement
        style_value = tag.get("style")
        if style_value:
            tag["style"] = _rewrite_css_urls(
                style_value,
                source_deck_id=source_deck_id,
                target_deck_id=target_deck_id,
                asset_paths=asset_paths,
            )
    for style_tag in soup.find_all("style"):
        if not style_tag.string:
            continue
        style_tag.string = _rewrite_css_urls(
            style_tag.string,
            source_deck_id=source_deck_id,
            target_deck_id=target_deck_id,
            asset_paths=asset_paths,
        )
    return soup.decode(), asset_paths


def _copy_imported_assets(
    *,
    source_path: Path,
    target_path: Path,
    asset_paths: set[str],
) -> None:
    if not asset_paths:
        return
    source_assets = (source_path / "assets").resolve()
    if not source_assets.exists():
        LOGGER.warning("Source deck assets missing at %s", source_assets)
        return
    target_assets = (target_path / "assets").resolve()
    target_assets.mkdir(parents=True, exist_ok=True)
    for relative in sorted(asset_paths):
        source_file = (source_assets / relative).resolve()
        try:
            source_file.relative_to(source_assets)
        except ValueError:
            LOGGER.warning("Skipped unsafe asset path %s while importing", source_file)
            continue
        if not source_file.exists():
            LOGGER.warning("Asset %s missing in source deck", source_file)
            continue
        target_file = target_assets / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)


def write_index_html(deck_path: Path, slides: Iterable[Slide]) -> None:
    slide_list = list(slides)
    slide_files = [slide.id for slide in slide_list]
    slides_json = json.dumps(slide_files)
    deck_name = deck_path.name
    content = INDEX_VIEWER_TEMPLATE.replace("__DECK_NAME__", deck_name).replace(
        "__SLIDES_ARRAY__", slides_json
    )
    (deck_path / INDEX_HTML).write_text(content, encoding="utf-8")


def _write_index_json(deck_path: Path, deck: Deck) -> None:
    payload_slides: list[dict[str, object] | str] = []
    for slide in deck.slides:
        if slide.kind == "normal" and not slide.section_id and not slide.subsection_id:
            payload_slides.append(slide.id)
            continue
        payload_slides.append(
            {
                "file": slide.id,
                "kind": slide.kind,
                "sectionId": slide.section_id,
                "subsectionId": slide.subsection_id,
            }
        )
    payload: dict[str, object] = {
        "slides": payload_slides,
        "promptStyle": deck.prompt_style,
    }
    if deck.owner_email is not None:
        payload["ownerEmail"] = deck.owner_email
    if deck.shared_with:
        payload["sharedWith"] = list(deck.shared_with)
    if deck.sections:
        payload["sections"] = [
            {
                "id": section.id,
                "title": section.title,
                "startSlide": section.start_slide,
                "subsections": [
                    {
                        "id": subsection.id,
                        "title": subsection.title,
                        "startSlide": subsection.start_slide,
                    }
                    for subsection in section.subsections
                ],
            }
            for section in deck.sections
        ]
    (deck_path / INDEX_JSON).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_slide_html(slide: Slide) -> str:
    """Render ``slide`` back to a standalone HTML document."""

    updated_html = update_slide_document(
        slide.full_html,
        title_html=slide.title_html,
        body_html=slide.body_html,
        notes_html=slide.notes_html,
        source_html=slide.source_html,
    )
    slide.full_html = updated_html
    return updated_html


def _write_section_styles(deck_path: Path, deck: Deck) -> None:
    if not any(slide.kind == "sectionHeader" for slide in deck.slides):
        return
    target = deck_path / "section_header.css"
    source = Path("static/css/section_header_viewer.css")
    if source.exists():
        style = load_notebooklm_style(deck.prompt_style)
        css_vars = build_notebooklm_css_variables(style)
        target.write_text(
            f"{css_vars}\n{source.read_text(encoding='utf-8')}", encoding="utf-8"
        )
