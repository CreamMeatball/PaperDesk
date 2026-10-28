import { pref, setPref } from "./prefs.js";
import { h, icon, iconButton, toast, MOD, modKey } from "./ui.js";
import { CitationPreview, ReferenceIndex } from "./references.js";
import { analyzeDocument } from "./layout.js";
import { TextMap } from "./textmap.js";
import { TranslationController } from "./translation.js";
import { Visuals } from "./visuals.js";
import { Annotations, COLORS } from "./annotations.js";
import { FindBar } from "./find.js";
import { Navigator } from "./navigator.js";
import { AreaSelect } from "./area.js";
import { t } from "./i18n.js";

var pdfjsPromise = null;
export function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import("/vendor/pdfjs/pdf.min.mjs").then(function (lib) {
      lib.GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/pdf.worker.min.mjs";
      return lib;
    });
  }
  return pdfjsPromise;
}

var MIN_ZOOM = 0.5, MAX_ZOOM = 3, GAP = 18, TCOL_RATIO = 0.72;

// PDF viewer core. Features plug in as objects with optional hooks:
//   onAnalysis()            document analysis (blocks, figures, sections) is ready
//   onPageRender(state)     a page's canvas and text layer were (re)drawn
//   onScroll(), destroy()
export class ReaderView {
  constructor(root, app, route) {
    this.root = root;
    this.app = app;
    this.id = route.id;
    this.startPage = route.page || 1;
    this.zoom = 1;
    this.fitScale = 1;
    this.pages = [];
    this.texts = [];
    this.current = 1;
    this.alive = true;
    this.analysis = null;
    this.references = null;
    this.tmode = pref("translation_mode", "side");
    this.onSelection = this.onSelection.bind(this);
    this.onKey = this.onKey.bind(this);
    this.onResize = this.onResize.bind(this);
    this.render();
    this.load();
  }

  get scale() { return this.fitScale * this.zoom; }
  get plugins() { return [this.annotations, this.translation, this.visuals, this.citations, this.find, this.nav, this.area]; }
  each(method, arg) {
    this.plugins.forEach(function (plugin) {
      if (plugin && plugin[method]) {
        try { plugin[method](arg); } catch (error) { console.warn(method, error); }
      }
    });
  }

  destroy() {
    this.alive = false;
    if (this.observer) this.observer.disconnect();
    document.removeEventListener("selectionchange", this.onSelection);
    document.removeEventListener("keydown", this.onKey);
    window.removeEventListener("resize", this.onResize);
    this.hideMenu();
    this.each("destroy");
    if (this.pdf) this.pdf.destroy();
    this.app.assistant.attach(null);
  }

  render() {
    var self = this, app = this.app;
    var doc = app.store.document(this.id);
    this.pageInput = h("input", { class: "page-input", value: "1", "aria-label": t("쪽"),
      onkeydown: function (event) { if (event.key === "Enter") self.goToPage(parseInt(self.pageInput.value, 10)); } });
    this.totalLabel = h("span", { class: "sub" }, "/ —");
    this.zoomLabel = h("span", { class: "zoom-label" }, "100%");
    this.titleEl = h("h1", { title: t("더블클릭해 이름 바꾸기"), ondblclick: function () { var d = app.store.document(self.id); if (d) app.renameDocument(d); } },
      doc ? doc.title : t("불러오는 중…"));
    this.pagesEl = h("div", { class: "pages", tabindex: "-1" }, h("div", { class: "loading" }, t("PDF를 여는 중…")));
    this.bodyEl = h("div", { class: "reader-body" }, this.pagesEl);
    this.readerEl = h("div", { class: "reader" });

    this.annotations = new Annotations(this);
    this.citations = new CitationPreview(this, app);
    this.translation = new TranslationController(this);
    this.visuals = new Visuals(this);
    this.find = new FindBar(this);
    this.nav = new Navigator(this);
    this.area = new AreaSelect(this);

    var toolbar = h("div", { class: "toolbar" },
      app.sidebarHidden() ? iconButton("sidebar", t("사이드바 보이기"), function () { app.toggleSidebar(); }) : null,
      iconButton("back", t("서재로"), function () { app.backToLibrary(); }),
      this.nav.button,
      this.titleEl,
      h("span", { class: "spacer" }),
      this.find.button, this.area.button, this.translation.button,
      h("span", { class: "tb-sep" }),
      this.pageInput, this.totalLabel,
      h("span", { class: "tb-sep" }),
      iconButton("minus", t("축소"), function () { self.setZoom(self.zoom / 1.15); }),
      this.zoomLabel,
      iconButton("plus", t("확대"), function () { self.setZoom(self.zoom * 1.15); }),
      iconButton("fit", t("창에 맞추기"), function () { self.setZoom(1); }),
      h("span", { class: "tb-sep" }),
      iconButton("panel", t("AI 도우미 ({key})", { key: MOD + "J" }), function () { app.toggleAssistant(); }));
    this.pagesEl.addEventListener("scroll", function () { self.onScroll(); }, { passive: true });
    this.readerEl.replaceChildren(toolbar, this.bodyEl);
    this.root.replaceChildren(this.readerEl);
    document.addEventListener("selectionchange", this.onSelection);
    document.addEventListener("keydown", this.onKey);
    window.addEventListener("resize", this.onResize);
    app.assistant.attach(this);
  }

  async load() {
    var app = this.app;
    try {
      var opened = await app.api.post("/api/documents/" + this.id + "/open");
      this.doc = opened.document;
      this.titleEl.textContent = this.doc.title;
      var lib = await loadPdfjs();
      this.lib = lib;
      this.pdf = await lib.getDocument({ url: "/api/documents/" + this.id + "/file", isEvalSupported: false }).promise;
      if (!this.alive) { this.pdf.destroy(); return; }
      this.adoptEmbeddedTitle();
      var sizes = [];
      for (var n = 1; n <= this.pdf.numPages; n++) {
        var page = await this.pdf.getPage(n);
        var viewport = page.getViewport({ scale: 1 });
        sizes.push({ width: viewport.width, height: viewport.height });
      }
      if (!this.alive) return;
      this.totalLabel.textContent = "/ " + this.pdf.numPages;
      this.buildPages(sizes);
      if (this.startPage > 1) this.goToPage(this.startPage);
      this.extractText();
    } catch (error) {
      if (!this.alive) return;
      this.pagesEl.replaceChildren(h("div", { class: "loading" }, t("PDF를 열지 못했어요: {error}", { error: error.message || error })));
      if (error.status === 404) { toast(t("논문을 찾지 못했어요."), true); app.backToLibrary(); }
    }
  }

  // Imported files are titled after their filename; on first open, prefer the title stored inside the PDF.
  async adoptEmbeddedTitle() {
    var doc = this.doc, stem = doc.filename.replace(/\.pdf$/i, "").replace(/_/g, " ").trim();
    if (doc.title !== stem) return;
    try {
      var meta = await this.pdf.getMetadata();
      var title = ((meta.info && meta.info.Title) || "").replace(/\s+/g, " ").trim();
      if (title.length < 6 || title.length > 200 || /^(untitled|microsoft word|title|paper)\b/i.test(title) || /\.(pdf|docx?|tex)$/i.test(title)) return;
      await this.app.store.renameDocument(doc.id, title);
      this.doc.title = title;
      if (this.alive) this.titleEl.textContent = title;
    } catch (error) { console.warn("title lookup failed", error); }
  }

  // ---------- layout ----------
  computeFit() {
    var widest = Math.max.apply(null, this.pages.map(function (p) { return p.size.width; }));
    var available = Math.max(320, this.pagesEl.clientWidth - 72);
    if (this.tmode === "side") available = (available - GAP) / (1 + TCOL_RATIO);
    return Math.max(0.35, Math.min(2.2, available / widest));
  }

  buildPages(sizes) {
    var self = this;
    this.pages = sizes.map(function (size, index) {
      var number = index + 1;
      var el = h("div", { class: "page", "data-page": String(number) },
        h("canvas"), h("div", { class: "layer marks" }), h("div", { class: "layer flash" }), h("div", { class: "textLayer" }),
        h("div", { class: "layer over" }), h("div", { class: "layer ui" }), h("span", { class: "page-no" }, String(number)));
      var tcol = h("div", { class: "tcol" });
      var row = h("div", { class: "page-row", "data-page": String(number) }, el, tcol);
      return { number: number, size: size, el: el, tcol: tcol, row: row, rendered: 0, busy: false, hotspots: [] };
    });
    this.pagesEl.replaceChildren.apply(this.pagesEl, this.pages.map(function (p) { return p.row; }));
    this.fitScale = this.computeFit();
    this.sizePages();
    this.observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) self.renderPage(self.pages[Number(entry.target.dataset.page) - 1]);
      });
    }, { root: this.pagesEl, rootMargin: "900px 0px" });
    this.pages.forEach(function (p) { self.observer.observe(p.row); });
    this.each("onPagesBuilt");
  }

  sizePages() {
    var scale = this.scale, side = this.tmode === "side";
    this.readerEl.dataset.tmode = this.tmode;
    this.pages.forEach(function (p) {
      var width = Math.floor(p.size.width * scale), height = Math.floor(p.size.height * scale);
      p.el.style.width = width + "px";
      p.el.style.height = height + "px";
      p.el.style.setProperty("--scale-factor", scale);
      p.el.style.setProperty("--user-unit", "1");
      p.el.style.setProperty("--total-scale-factor", scale);
      p.tcol.style.width = side ? Math.max(260, Math.round(width * TCOL_RATIO)) + "px" : "0px";
      p.tcol.style.minHeight = height + "px";
    });
    this.zoomLabel.textContent = Math.round(this.zoom * 100) + "%";
  }

  relayout() {
    var anchor = this.pages[this.current - 1], offset = 0;
    if (anchor) offset = (this.pagesEl.scrollTop - anchor.row.offsetTop) / Math.max(1, anchor.row.offsetHeight);
    this.sizePages();
    this.pages.forEach(function (p) { p.rendered = 0; p.map = null; });
    if (anchor) this.pagesEl.scrollTop = anchor.row.offsetTop + offset * anchor.row.offsetHeight;
    var self = this;
    this.visiblePages().forEach(function (p) { self.renderPage(p); });
  }

  setTranslationMode(mode) {
    if (mode === this.tmode) return;
    this.tmode = mode;
    setPref("translation_mode", mode);
    this.fitScale = this.computeFit();
    this.relayout();
  }

  setZoom(value) {
    this.zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value));
    this.relayout();
  }

  onResize() {
    if (!this.pages.length) return;
    clearTimeout(this.resizeTimer);
    var self = this;
    this.resizeTimer = setTimeout(function () {
      var fit = self.computeFit();
      if (Math.abs(fit - self.fitScale) > 0.01) { self.fitScale = fit; self.relayout(); }
    }, 120);
  }

  visiblePages(margin) {
    var pad = margin == null ? 600 : margin;
    var top = this.pagesEl.scrollTop - pad, bottom = this.pagesEl.scrollTop + this.pagesEl.clientHeight + pad;
    return this.pages.filter(function (p) { return p.row.offsetTop + p.row.offsetHeight > top && p.row.offsetTop < bottom; });
  }

  async renderPage(state) {
    if (!state || !this.pdf || state.rendered === this.scale || state.busy) return;
    state.busy = true;
    var scale = this.scale, self = this;
    try {
      var page = await this.pdf.getPage(state.number);
      var viewport = page.getViewport({ scale: scale });
      var ratio = Math.min(window.devicePixelRatio || 1, 2);
      var canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      await page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null }).promise;
      if (!this.alive || scale !== this.scale) return;
      state.el.querySelector("canvas").replaceWith(canvas);
      var layer = state.el.querySelector(".textLayer");
      layer.replaceChildren();
      await new this.lib.TextLayer({ textContentSource: page.streamTextContent(), container: layer, viewport: viewport }).render();
      state.rendered = scale;
      state.map = new TextMap(state.el);
      this.reindex(state);
      this.each("onPageRender", state);
    } catch (error) {
      if (!error || error.name !== "RenderingCancelledException") console.warn(error);
    } finally {
      state.busy = false;
      if (this.alive && state.rendered !== this.scale && this.visiblePages().indexOf(state) >= 0) {
        setTimeout(function () { self.renderPage(state); }, 30);
      }
    }
  }

  // Hover targets (citations, figure/table references) for one page.
  reindex(state) {
    if (!state.map) { state.hotspots = []; return; }
    var cites = this.references && this.references.ready ? this.references.hotspotsFor(state.el, state.number) : [];
    var visuals = this.analysis ? this.visuals.hotspotsFor(state) : [];
    state.hotspots = cites.map(function (spot) { spot.kind = "cite"; return spot; }).concat(visuals);
  }

  onScroll() {
    if (this.scrollFrame) return;
    var self = this;
    this.scrollFrame = requestAnimationFrame(function () {
      self.scrollFrame = 0;
      var middle = self.pagesEl.scrollTop + self.pagesEl.clientHeight * 0.35;
      for (var i = 0; i < self.pages.length; i++) {
        var p = self.pages[i];
        if (p.row.offsetTop + p.row.offsetHeight > middle) { self.setCurrent(p.number); break; }
      }
      self.hideMenu();
      self.each("onScroll");
    });
  }

  setCurrent(number) {
    if (number === this.current) return;
    this.current = number;
    if (document.activeElement !== this.pageInput) this.pageInput.value = String(number);
    this.each("onCurrentPage", number);
  }

  goToPage(number, fraction) {
    if (!this.pages.length || !number) return;
    var target = this.pages[Math.max(1, Math.min(this.pages.length, number)) - 1];
    var offset = fraction ? fraction * target.el.offsetHeight - this.pagesEl.clientHeight * 0.25 : -12;
    this.pagesEl.scrollTop = target.row.offsetTop + Math.max(-12, offset);
    this.setCurrent(target.number);
    this.pageInput.value = String(target.number);
  }

  // ---------- text & analysis ----------
  async extractText() {
    // Extract once: text for search/summaries/MCP, the layout analysis and the bibliography index.
    var texts = [], layout = [];
    try {
      for (var n = 1; n <= this.pdf.numPages; n++) {
        var page = await this.pdf.getPage(n);
        var content = await page.getTextContent();
        layout.push({ width: page.view[2] - page.view[0], height: page.view[3] - page.view[1], view: page.view, items: content.items });
        texts.push(content.items.map(function (item) { return (item.str || "") + (item.hasEOL ? "\n" : " "); }).join("")
          .replace(/[ \t]+\n/g, "\n").replace(/ {2,}/g, " ").trim());
        if (!this.alive) return;
      }
      this.texts = texts;
      this.references = ReferenceIndex.build(layout);
      this.analysis = analyzeDocument(layout);
      var self = this;
      this.each("onAnalysis");
      this.app.assistant.onAnalysis();
      this.pages.forEach(function (p) {
        if (p.rendered && p.map) { self.reindex(p); self.each("onPageRender", p); }
      });
      if (!this.doc || this.doc.text_pages !== texts.length) {
        await this.app.api.put("/api/documents/" + this.id + "/text", { pages: texts });
        this.app.store.load();
      }
    } catch (error) {
      console.warn("text extraction failed", error);
    }
  }

  pageText(number) { return this.texts[(number || this.current) - 1] || ""; }
  title() { return this.doc ? this.doc.title : ""; }

  // Body text for summaries: analysis paragraphs without references, page furniture or figure labels.
  paperText(limit) {
    var out = "", page = 0;
    if (this.analysis) {
      for (var i = 0; i < this.analysis.blocks.length; i++) {
        var b = this.analysis.blocks[i];
        if (!b.translatable && b.kind !== "equation") continue;
        if (b.page !== page) { page = b.page; out += "\n\n[page " + page + "]\n"; }
        out += (b.kind === "heading" ? "\n## " : "") + b.text + "\n";
        if (out.length > limit) return out.slice(0, limit) + "\n[truncated]";
      }
      return out.trim();
    }
    var joined = this.texts.map(function (t, i) { return "[page " + (i + 1) + "]\n" + t; }).join("\n\n");
    return joined.length > limit ? joined.slice(0, limit) + "\n[truncated]" : joined;
  }

  // Text around a block (for equation explanations): ~before chars before and ~after chars after.
  textAround(key, before, after) {
    var blocks = this.analysis ? this.analysis.blocks : [], at = blocks.findIndex(function (b) { return b.key === key; });
    if (at < 0) return "";
    var head = "", tail = "";
    for (var i = at - 1; i >= 0 && head.length < before; i--) if (blocks[i].translatable || blocks[i].kind === "equation") head = blocks[i].text + "\n" + head;
    for (var j = at + 1; j < blocks.length && tail.length < after; j++) if (blocks[j].translatable || blocks[j].kind === "equation") tail += blocks[j].text + "\n";
    return head.slice(-before) + "\n[THIS ITEM]\n" + tail.slice(0, after);
  }

  // Canvas crop of a page area (fractions) as a PNG data URL. Renders offscreen when the page is not on screen.
  async cropImage(pageNumber, rect, maxWidth) {
    var state = this.pages[pageNumber - 1], source = state && state.rendered ? state.el.querySelector("canvas") : null;
    var limit = maxWidth || 1600, pad = 0.006;
    var r = [Math.max(0, rect[0] - pad), Math.max(0, rect[1] - pad), Math.min(1, rect[2] + pad), Math.min(1, rect[3] + pad)];
    if (!source || source.width < 900) {
      var page = await this.pdf.getPage(pageNumber);
      var base = page.getViewport({ scale: 1 });
      var scale = Math.min(3, Math.max(1.5, limit / (base.width * (r[2] - r[0]))));
      var viewport = page.getViewport({ scale: scale });
      source = document.createElement("canvas");
      source.width = Math.floor(viewport.width);
      source.height = Math.floor(viewport.height);
      await page.render({ canvasContext: source.getContext("2d"), viewport: viewport }).promise;
    }
    var sx = r[0] * source.width, sy = r[1] * source.height, sw = (r[2] - r[0]) * source.width, sh = (r[3] - r[1]) * source.height;
    var ratio = Math.min(1, limit / sw);
    var out = document.createElement("canvas");
    out.width = Math.max(1, Math.round(sw * ratio));
    out.height = Math.max(1, Math.round(sh * ratio));
    var ctx = out.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(source, sx, sy, sw, sh, 0, 0, out.width, out.height);
    return out.toDataURL("image/png");
  }

  flashRect(pageNumber, rect, scroll) {
    var state = this.pages[pageNumber - 1];
    if (!state) return;
    if (scroll) this.goToPage(pageNumber, rect[1]);
    var layer = state.el.querySelector(".layer.flash");
    var box = h("div", { class: "flash-box", style: "left:" + rect[0] * 100 + "%;top:" + rect[1] * 100 + "%;width:" + (rect[2] - rect[0]) * 100 + "%;height:" + (rect[3] - rect[1]) * 100 + "%" });
    layer.append(box);
    setTimeout(function () { box.remove(); }, 1700);
  }

  // ---------- selection menu ----------
  selectionInfo() {
    var selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
    var range = selection.getRangeAt(0);
    var node = range.commonAncestorContainer;
    var element = node.nodeType === 1 ? node : node.parentElement;
    if (!element || !this.pagesEl.contains(element) || element.closest(".tcol, .layer.over")) return null;
    var text = selection.toString().replace(/\s+/g, " ").trim();
    if (text.length < 2) return null;
    var pageEl = (range.startContainer.parentElement && range.startContainer.parentElement.closest(".page")) || element.closest(".page");
    var page = pageEl ? Number(pageEl.dataset.page) : this.current;
    var state = this.pages[page - 1], rects = [];
    if (state && state.map) {
      rects = state.map.normalize(range).filter(function (r) { return r[2] > 0 && r[0] < 1 && r[3] > 0 && r[1] < 1; });
    }
    return { text: text, page: page, rect: range.getBoundingClientRect(), rects: rects };
  }

  onSelection() {
    clearTimeout(this.selectionTimer);
    var self = this;
    this.selectionTimer = setTimeout(function () {
      var info = self.selectionInfo();
      if (info) self.showMenu(info); else if (!self.menuPinned) self.hideMenu();
    }, 180);
  }

  runSelection(action, info, color) {
    var app = this.app;
    this.hideMenu();
    if (!info) return;
    if (action === "translate" || action === "explain" || action === "define") app.assistant.runOnSelection(action, info);
    else if (action === "ask") app.assistant.quote(info);
    else if (action === "highlight") this.annotations.create(info, "highlight", color);
    else if (action === "note") this.annotations.createNote(info);
    else if (action === "reading") app.addToReadingList(info.text, this.id);
    else if (action === "copy") { navigator.clipboard.writeText(info.text); toast(t("복사했어요")); }
    if (action !== "ask") window.getSelection().removeAllRanges();
  }

  showMenu(info) {
    var self = this;
    this.hideMenu();
    this.selection = info;
    function item(action, iconName, label, key) {
      return h("button", { title: t(label) + (key ? " (" + key + ")" : ""), onclick: function () { self.runSelection(action, info); } },
        icon(iconName), t(label), key ? h("kbd", null, key) : null);
    }
    var swatches = h("span", { class: "swatches" }, COLORS.map(function (color) {
      return h("button", { class: "swatch " + color, title: t("하이라이트"), "aria-label": t("하이라이트") + " " + color,
        onclick: function () { self.runSelection("highlight", info, color); } });
    }));
    this.menu = h("div", { class: "selection-menu", role: "toolbar" },
      item("translate", "translate", t("번역"), "T"), item("explain", "sparkle", t("설명"), "E"), item("define", "book", t("뜻"), "W"),
      item("ask", "question", t("질문"), "Q"),
      h("span", { class: "menu-sep" }),
      h("span", { class: "hl-group", title: t("하이라이트 (H)") }, icon("highlighter"), swatches),
      item("note", "note", t("메모"), "C"),
      h("span", { class: "menu-sep" }),
      h("button", { title: t("선택한 참고문헌을 읽어볼 논문에 추가"), onclick: function () { self.runSelection("reading", info); } }, icon("bookmark")),
      h("button", { title: t("복사"), onclick: function () { self.runSelection("copy", info); } }, icon("copy")));
    this.menu.addEventListener("mousedown", function (event) { event.preventDefault(); });
    document.body.append(this.menu);
    this.placeMenu(this.menu, info.rect);
  }

  placeMenu(menu, rect) {
    var box = menu.getBoundingClientRect();
    var top = rect.top - box.height - 8;
    if (top < 8) top = rect.bottom + 8;
    menu.style.top = top + "px";
    menu.style.left = Math.max(8, Math.min(innerWidth - box.width - 8, rect.left + rect.width / 2 - box.width / 2)) + "px";
  }

  hideMenu() {
    if (this.menu) { this.menu.remove(); this.menu = null; }
  }

  onKey(event) {
    if (modKey(event) && event.key.toLowerCase() === "f") { event.preventDefault(); this.find.open(); return; }
    var target = event.target;
    var typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
    if (event.key === "Escape" && !typing) { this.hideMenu(); this.area.exit(); return; }
    if (!this.menu || event.metaKey || event.ctrlKey || event.altKey || typing) return;
    var map = { t: "translate", e: "explain", w: "define", q: "ask", h: "highlight", c: "note", enter: "ask" };
    var action = map[event.key.toLowerCase()];
    if (action) { event.preventDefault(); this.runSelection(action, this.selection); }
  }
}
