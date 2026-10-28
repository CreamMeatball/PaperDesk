import { h, icon, iconButton, MOD } from "./ui.js";
import { drawRects } from "./textmap.js";

// Find in document (Cmd/Ctrl+F): whitespace-insensitive, case-insensitive, highlights on rendered pages.
export class FindBar {
  constructor(reader) {
    this.reader = reader;
    this.hits = [];
    this.index = -1;
    var self = this;
    this.button = iconButton("search", "문서에서 찾기 (" + MOD + "F)", function () { self.open(); });
    this.input = h("input", { class: "find-input", placeholder: "문서에서 찾기", "aria-label": "문서에서 찾기",
      oninput: function () { clearTimeout(self.timer); self.timer = setTimeout(function () { self.search(); }, 150); },
      onkeydown: function (event) {
        if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); self.step(event.shiftKey ? -1 : 1); }
        if (event.key === "Escape") { event.preventDefault(); self.close(); }
      } });
    this.count = h("span", { class: "find-count" });
    this.bar = h("div", { class: "find-bar", hidden: true }, icon("search", 14), this.input, this.count,
      iconButton("chevronUp", "이전 (⇧⏎)", function () { self.step(-1); }),
      iconButton("chevronDown", "다음 (⏎)", function () { self.step(1); }),
      iconButton("close", "닫기 (Esc)", function () { self.close(); }));
    reader.bodyEl.append(this.bar);
  }

  open() {
    this.bar.hidden = false;
    var selected = window.getSelection().toString().trim();
    if (selected && selected.length < 80) { this.input.value = selected; this.search(); }
    this.input.focus();
    this.input.select();
  }

  close() {
    this.bar.hidden = true;
    this.hits = [];
    this.index = -1;
    this.redrawAll();
    this.reader.pagesEl.focus();
  }

  search() {
    var needle = this.input.value.replace(/[\s\u00ad]+/g, "").toLowerCase(), hits = [];
    if (needle.length >= 1) {
      this.reader.texts.forEach(function (text, i) {
        var hay = text.replace(/[\s\u00ad]+/g, "").toLowerCase(), at = hay.indexOf(needle);
        while (at >= 0 && hits.length < 2000) { hits.push({ page: i + 1, start: at, end: at + needle.length }); at = hay.indexOf(needle, at + 1); }
      });
    }
    this.hits = hits;
    this.index = hits.length ? this.firstAfterCurrent() : -1;
    this.updateCount();
    this.redrawAll();
    if (this.index >= 0) this.reveal();
  }

  firstAfterCurrent() {
    var current = this.reader.current;
    var at = this.hits.findIndex(function (hit) { return hit.page >= current; });
    return at < 0 ? 0 : at;
  }

  updateCount() {
    this.count.textContent = this.input.value.trim() ? (this.hits.length ? (this.index + 1) + "/" + this.hits.length : "없음") : "";
  }

  step(direction) {
    if (!this.hits.length) return;
    this.index = (this.index + direction + this.hits.length) % this.hits.length;
    this.updateCount();
    this.redrawAll();
    this.reveal();
  }

  reveal() {
    var hit = this.hits[this.index], state = this.reader.pages[hit.page - 1], self = this;
    if (!state) return;
    var rects = state.map ? state.map.rects(hit.start, hit.end) : [];
    this.reader.goToPage(hit.page, rects.length ? rects[0][1] : 0);
    if (!state.map) setTimeout(function () { self.redrawAll(); }, 400);
  }

  redrawAll() {
    var self = this;
    this.reader.pages.forEach(function (state) { if (state.map) self.onPageRender(state); });
  }

  onPageRender(state) {
    var layer = state.el.querySelector(".layer.flash"), self = this;
    layer.querySelectorAll(".find-hit").forEach(function (n) { n.remove(); });
    if (this.bar.hidden || !state.map) return;
    this.hits.forEach(function (hit, i) {
      if (hit.page !== state.number) return;
      drawRects(layer, state.map.rects(hit.start, hit.end), "find-hit" + (i === self.index ? " current" : ""));
    });
  }
}

