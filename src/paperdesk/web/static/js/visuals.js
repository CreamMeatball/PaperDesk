import { h, icon, toast } from "./ui.js";
import { rectContains } from "./textmap.js";
import { t } from "./i18n.js";

var NAMES = { figure: "그림", table: "표", algorithm: "알고리즘", equation: "식" };
var MENTION = /\b(Figures?|Figs?\.|Tables?|Tabs?\.|Algorithms?|Alg\.)\s*~?\s*(\d+|[A-Z]\.\d+)(?:\s*\(?([a-z])\)?(?![A-Za-z]))?|\b(Eqs?\.|Equations?)\s*~?\s*\(?(\d+)\)?/g;

function kindOf(word) { return /^tab/i.test(word) ? "table" : /^alg/i.test(word) ? "algorithm" : "figure"; }
export function visualName(target) {
  return target.kind === "equation" ? (target.number ? t("식 ({n})", { n: target.number }) : t("식")) : t(NAMES[target.kind]) + " " + target.label;
}

// Figures, tables, algorithms and equations: hover outlines with explain buttons, and previews for in-text references.
export class Visuals {
  constructor(reader) {
    this.reader = reader;
    this.app = reader.app;
    this.targets = new Map();
    this.images = new Map();
    var self = this;
    this.box = h("div", { class: "visual-hover" });
    this.button = h("button", { class: "visual-btn", onmousedown: function (e) { e.preventDefault(); }, onclick: function (e) { e.stopPropagation(); self.explain(self.current); } });
    this.box.append(this.button);
    this.onMove = this.onMove.bind(this);
    reader.pagesEl.addEventListener("mousemove", this.onMove);
    reader.pagesEl.addEventListener("mouseleave", function () { self.scheduleHide(); });
  }

  destroy() { clearTimeout(this.hideTimer); this.box.remove(); }

  onScroll() { clearTimeout(this.hideTimer); this.hideTimer = null; this.box.remove(); this.current = null; }

  onAnalysis() {
    var self = this, analysis = this.reader.analysis;
    this.targets.clear();
    analysis.regions.forEach(function (r) {
      var key = r.kind + ":" + r.label;
      if (!self.targets.has(key)) self.targets.set(key, r);
    });
    analysis.equations.forEach(function (e) {
      e.kind = "equation";
      if (e.number && !self.targets.has("equation:" + e.number)) self.targets.set("equation:" + e.number, e);
    });
  }

  find(kind, label) { return this.targets.get(kind + ":" + String(label).replace(/^([A-Z])\.?(\d)/, "$1.$2")) || null; }

  // ---------- hotspots for "Figure 3", "Table 2", "Eq. (4)" in the PDF text ----------
  hotspotsFor(state) {
    var map = state.map, spots = [], match, self = this;
    if (!map || !this.targets.size) return spots;
    var captions = this.reader.analysis.pages[state.number - 1].blocks.filter(function (b) { return b.kind === "caption"; });
    MENTION.lastIndex = 0;
    while ((match = MENTION.exec(map.spaced))) {
      var target = match[1] ? self.find(kindOf(match[1]), match[2]) : self.find("equation", match[5]);
      if (!target) continue;
      var rects = map.spacedRects(match.index, match.index + match[0].length);
      if (!rects.length) continue;
      var first = rects[0];
      var own = captions.some(function (c) { return rectContains(c.rect, first[0], first[1], 0.002, 0.002) && Math.abs(first[1] - c.rect[1]) < 0.012; });
      if (own) continue; // the caption's own "Figure 3:" label
      spots.push({ kind: "visual", target: target, rects: rects, label: match[0] });
    }
    return spots;
  }

  imageFor(target) {
    var rect = target.imageRect || target.rect, key = target.page + ":" + rect.join(","), self = this;
    if (!this.images.has(key)) {
      var pending = this.reader.cropImage(target.page, rect, 900).catch(function (error) { self.images.delete(key); throw error; });
      this.images.set(key, pending);
    }
    return this.images.get(key);
  }

  // Same-page references pulse in the original; other pages show a cropped preview.
  previewContent(target, hoveredPage) {
    var self = this;
    if (target.page === hoveredPage) {
      this.reader.flashRect(target.page, target.rect, false, true);
      return null;
    }
    var img = h("img", { class: "visual-img", alt: visualName(target) });
    this.imageFor(target).then(function (url) { if (self.reader.alive) img.src = url; }).catch(function (error) { console.warn(error); });
    return h("div", { class: "visual-preview" },
      h("div", { class: "cite-label" }, visualName(target), h("span", null, " · " + t("{n}쪽", { n: target.page }))),
      img,
      target.caption && target.kind !== "equation" ? h("div", { class: "visual-caption" }, target.caption) : null,
      h("div", { class: "cite-actions" },
        h("button", { class: "btn small", onclick: function () { self.reader.citations.hide(); self.reader.flashRect(target.page, target.rect, true); } }, icon("chevron", 13), t("{n}쪽으로 이동", { n: target.page })),
        h("button", { class: "btn small", onclick: function () { self.reader.citations.hide(); self.explain(target); } }, icon("sparkle", 13), t("{name} 설명", { name: visualName(target) }))));
  }

  // ---------- hover outline + explain button ----------
  onMove(event) {
    if (event.buttons || !this.reader.analysis || this.reader.area.active) return;
    if (event.target.closest && event.target.closest(".visual-hover")) { clearTimeout(this.hideTimer); this.hideTimer = null; return; }
    var pageEl = event.target.closest && event.target.closest(".page");
    if (!pageEl) { this.scheduleHide(); return; }
    var box = pageEl.getBoundingClientRect(), px = (event.clientX - box.left) / box.width, py = (event.clientY - box.top) / box.height;
    var page = Number(pageEl.dataset.page), analysis = this.reader.analysis;
    var hit = analysis.equations.find(function (e) { return e.page === page && rectContains(e.rect, px, py, 0.05, 0.004); }) ||
      analysis.regions.find(function (r) { return r.page === page && rectContains(r.rect, px, py, 0, 0); });
    if (hit) this.show(pageEl, hit); else this.scheduleHide();
  }

  show(pageEl, target) {
    clearTimeout(this.hideTimer);
    this.hideTimer = null;
    if (this.current === target && this.box.parentNode) return;
    this.current = target;
    var layer = pageEl.querySelector(".layer.ui"), r = target.rect;
    layer.append(this.box);
    this.box.className = "visual-hover " + target.kind;
    this.box.style.cssText = "left:" + r[0] * 100 + "%;top:" + r[1] * 100 + "%;width:" + (r[2] - r[0]) * 100 + "%;height:" + (r[3] - r[1]) * 100 + "%";
    this.button.replaceChildren(target.kind === "equation" ? "∑" : icon("sparkle", 13), " " + t("{name} 설명", { name: visualName(target) }));
  }

  scheduleHide() {
    if (this.hideTimer) return;
    var self = this;
    this.hideTimer = setTimeout(function () { self.hideTimer = null; self.box.remove(); self.current = null; }, 120);
  }

  mentions(target) {
    if (target.kind === "equation") return "";
    var words = target.kind === "table" ? "Tables?|Tabs?\\." : target.kind === "algorithm" ? "Algorithms?|Alg\\." : "Figures?|Figs?\\.";
    var re = new RegExp("\\b(" + words + ")\\s*~?\\s*" + target.label.replace(".", "\\.") + "\\b");
    return this.reader.analysis.blocks.filter(function (b) { return b.kind === "paragraph" && re.test(b.text); })
      .slice(0, 4).map(function (b) { return b.text; }).join("\n\n");
  }

  async explain(target) {
    if (!target) return;
    var reader = this.reader;
    this.box.remove();
    var image;
    try { image = await reader.cropImage(target.page, target.imageRect || target.rect, 1600); } catch (error) { console.warn(error); }
    var request = target.kind === "equation"
      ? { task: "equation", text: target.text, context: reader.textAround(target.key, 3500, 1500) }
      : { task: "figure", text: target.caption || visualName(target), context: this.mentions(target) };
    request.images = image ? [image] : [];
    request.label = visualName(target);
    request.page = target.page;
    request.thumb = image;
    this.app.assistant.runVisual(request);
  }
}

