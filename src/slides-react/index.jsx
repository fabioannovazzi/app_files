import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

function readBootstrapConfig() {
  const script = document.getElementById("slidesEditorBootstrap");
  if (!script || !script.textContent) {
    return {};
  }
  try {
    return JSON.parse(script.textContent);
  } catch (error) {
    return {};
  }
}

const bootstrap = readBootstrapConfig();
const rootElement = document.getElementById("slidesReactApp");

if (rootElement) {
  const root = createRoot(rootElement);
  root.render(<App bootstrap={bootstrap} />);
}
