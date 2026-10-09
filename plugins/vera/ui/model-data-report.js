"use strict";
/* Fixed Markdown presentation preserves canonical report text, without HTML or links. */
globalThis.VeraModelDataReport = Object.freeze({
  render(parent, markdown, api) {
    if (typeof markdown !== "string" || !markdown.trim()) {
      throw new Error("Il report dati leggibile conservato non è disponibile.");
    }
    const section = api.node("section", undefined, "model-data-report");
    let list = null, paragraph = [];
    function flush() {
      if (paragraph.length) {
        section.append(api.node("p", paragraph.join("\n"), "source-excerpt"));
        paragraph = [];
      }
    }
    // Mechanical rendering only: never classify phases, total unlike units,
    // translate retained text, infer exposure or interpret embedded markup.
    for (const line of markdown.split(/\r?\n/)) {
      const heading = /^(#{1,3}) (.*)$/.exec(line);
      if (!line) {
        flush();
        list = null;
      } else if (heading) {
        flush();
        list = null;
        section.append(api.node("h" + (heading[1].length + 1), heading[2], "source-excerpt"));
      } else if (line.startsWith("- ")) {
        flush();
        if (!list) {
          list = api.node("ul");
          section.append(list);
        }
        list.append(api.node("li", line.slice(2), "source-excerpt"));
      } else {
        list = null;
        paragraph.push(line);
      }
    }
    flush();
    parent.append(section);
    return section;
  }
});
