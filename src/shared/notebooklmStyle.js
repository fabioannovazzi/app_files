import styleTokens from "./notebooklm_style.json";

const FALLBACK_KEY = "uniform";

function normalizeStyleMap(tokens) {
  if (tokens && typeof tokens === "object" && tokens.styles && typeof tokens.styles === "object") {
    return tokens.styles;
  }
  return { [FALLBACK_KEY]: tokens };
}

const NOTEBOOKLM_STYLES = normalizeStyleMap(styleTokens);
const NOTEBOOKLM_STYLE_KEYS = Object.keys(NOTEBOOKLM_STYLES);

const defaultKeyCandidate =
  styleTokens && typeof styleTokens === "object" && typeof styleTokens.defaultKey === "string"
    ? styleTokens.defaultKey
    : FALLBACK_KEY;
const NOTEBOOKLM_DEFAULT_STYLE_KEY = NOTEBOOKLM_STYLES[defaultKeyCandidate]
  ? defaultKeyCandidate
  : NOTEBOOKLM_STYLE_KEYS[0] || FALLBACK_KEY;

export { NOTEBOOKLM_DEFAULT_STYLE_KEY, NOTEBOOKLM_STYLE_KEYS, NOTEBOOKLM_STYLES };

export function resolveNotebooklmStyleKey(styleKey) {
  const candidate = (styleKey || "").toString().trim().toLowerCase();
  if (candidate && NOTEBOOKLM_STYLES[candidate]) {
    return candidate;
  }
  return NOTEBOOKLM_DEFAULT_STYLE_KEY;
}

export function getNotebooklmStyle(styleKey) {
  const resolvedKey = resolveNotebooklmStyleKey(styleKey);
  return NOTEBOOKLM_STYLES[resolvedKey] || NOTEBOOKLM_STYLES[NOTEBOOKLM_DEFAULT_STYLE_KEY];
}

export function getNotebooklmFontStack(styleKeyOrTokens) {
  const style =
    styleKeyOrTokens && typeof styleKeyOrTokens === "object"
      ? styleKeyOrTokens
      : getNotebooklmStyle(styleKeyOrTokens);
  return `"${style.fontFamilyPrimary}", "${style.fontFamilyFallback}", sans-serif`;
}

export const NOTEBOOKLM_STYLE = getNotebooklmStyle(NOTEBOOKLM_DEFAULT_STYLE_KEY);
export const NOTEBOOKLM_FONT_STACK = getNotebooklmFontStack(NOTEBOOKLM_STYLE);
