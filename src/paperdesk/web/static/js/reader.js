import { h, icon, iconButton, toast, MOD } from "./ui.js";

var pdfjsPromise = null;
function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import("/vendor/pdfjs/pdf.min.mjs").then(function (lib) {
      lib.GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/pdf.worker.min.mjs";
      return lib;
    });
  }
  return pdfjsPromise;
}

var MIN_ZOOM = 0.5, MAX_ZOOM = 3;

// PDF viewer with lazy page rendering, selectable text and a selection menu that feeds the assistant.
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
    this.onSelection = this.onSelection.bind(this);
    this.onKey = this.onKey.bind(this);
    this.onResize = this.onResize.bind(this);
    this.render();
    this.load();
  }

  get scale() { return this.fitScale * this.zoom; }

  destroy() {
    this.alive = false;
    if (this.observer) this.observer.disconnect();
    document.removeEventListener("selectionchange", this.onSelection);
    document.removeEventListener("keydown", this.onKey);
    window.removeEventListener("resize", this.onResize);
    this.hideMenu();
    if (this.pdf) this.pdf.destroy();
    this.app.assistant.attach(null);
  }

  render() {
    var self = this, app = this.app;
    var doc = app.store.document(this.id);
    this.pageInput = h("input", { class: "page-input", value: "1", "aria-label": "쪽",
      onkeydown: function (event) { if (event.key === "Enter") self.goToPage(parseInt(self.pageInput.value, 10)); } });
    this.totalLabel = h("span", { class: "sub" }, "/ —");
    this.zoomLabel = h("span", { class: "zoom-label" }, "100%");
    this.titleEl = h("h1", { title: "더블클릭해 이름 바꾸기", ondblclick: function () { var d = app.store.document(self.id); if (d) app.renameDocument(d); } },
      doc ? doc.title : "불러오는 중…");
    var toolbar = h("div", { class: "toolbar" },
      app.sidebarHidden() ? iconButton("sidebar", "사이드바 보이기", function () { app.toggleSidebar(); }) : null,
      iconButton("back", "서재로", function () { app.backToLibrary(); }),
      this.titleEl,
      h("span", { class: "spacer" }),
      this.pageInput, this.totalLabel,
      h("span", { style: "width:10px" }),
      iconButton("minus", "축소", function () { self.setZoom(self.zoom / 1.15); }),
      this.zoomLabel,
      iconButton("plus", "확대", function () { self.setZoom(self.zoom * 1.15); }),
      iconButton("fit", "폭에 맞추기", function () { self.setZoom(1); }),
      h("span", { style: "width:6px" }),
      iconButton("panel", "AI 도우미 (" + MOD + "J)", function () { app.toggleAssistant(); }));
    this.pagesEl = h("div", { class: "pages", tabindex: "-1" }, h("div", { class: "loading" }, "PDF를 여는 중…"));
    this.pagesEl.addEventListener("scroll", function () { self.onScroll(); }, { passive: true });
    this.root.replaceChildren(h("div", { class: "reader" }, toolbar, this.pagesEl));
    document.addEventListener("selectionchange", this.onSelection);
    document.addEventListener("keydown", this.onKey);
    window.addEventListener("resize", this.onResize);
    app.assistant.attach(this);
  }

  async load() {
    var app = this.app, self = this;
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
      this.pagesEl.replaceChildren(h("div", { class: "loading" }, "PDF를 열지 못했어요: " + (error.message || error)));
      if (error.status === 404) { toast("논문을 찾지 못했어요.", true); app.backToLibrary(); }
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

  computeFit() {
    var widest = Math.max.apply(null, this.pages.map(function (p) { return p.size.width; }));
    var available = Math.max(320, this.pagesEl.clientWidth - 96);
    return Math.max(0.4, Math.min(2.2, available / widest));
  }

  buildPages(sizes) {
    var self = this;
    this.pages = sizes.map(function (size, index) {
      var el = h("div", { class: "page", "data-page": String(index + 1) },
        h("canvas"), h("div", { class: "textLayer" }), h("span", { class: "page-no" }, String(index + 1)));
      return { number: index + 1, size: size, el: el, rendered: 0, busy: false };
    });
    this.pagesEl.replaceChildren.apply(this.pagesEl, this.pages.map(function (p) { return p.el; }));
    this.fitScale = this.computeFit();
    this.sizePages();
    this.observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) self.renderPage(self.pages[Number(entry.target.dataset.page) - 1]);
      });
    }, { root: this.pagesEl, rootMargin: "900px 0px" });
    this.pages.forEach(function (p) { self.observer.observe(p.el); });
  }

  sizePages() {
    var scale = this.scale;
    this.pages.forEach(function (p) {
      p.el.style.width = Math.floor(p.size.width * scale) + "px";
      p.el.style.height = Math.floor(p.size.height * scale) + "px";
      p.el.style.setProperty("--scale-factor", scale);
      p.el.style.setProperty("--user-unit", "1");
      p.el.style.setProperty("--total-scale-factor", scale);
    });
    this.zoomLabel.textContent = Math.round(this.zoom * 100) + "%";
  }

  relayout() {
    var anchor = this.pages[this.current - 1], offset = 0;
    if (anchor) offset = (this.pagesEl.scrollTop - anchor.el.offsetTop) / Math.max(1, anchor.el.offsetHeight);
    this.sizePages();
    this.pages.forEach(function (p) { p.rendered = 0; });
    if (anchor) this.pagesEl.scrollTop = anchor.el.offsetTop + offset * anchor.el.offsetHeight;
    var self = this;
    this.visiblePages().forEach(function (p) { self.renderPage(p); });
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

  visiblePages() {
    var top = this.pagesEl.scrollTop - 600, bottom = this.pagesEl.scrollTop + this.pagesEl.clientHeight + 600;
    return this.pages.filter(function (p) { return p.el.offsetTop + p.el.offsetHeight > top && p.el.offsetTop < bottom; });
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
    } catch (error) {
      if (!error || error.name !== "RenderingCancelledException") console.warn(error);
    } finally {
      state.busy = false;
      if (this.alive && state.rendered !== this.scale && this.visiblePages().indexOf(state) >= 0) {
        setTimeout(function () { self.renderPage(state); }, 30);
      }
    }
  }

  onScroll() {
    if (this.scrollFrame) return;
    var self = this;
    this.scrollFrame = requestAnimationFrame(function () {
      self.scrollFrame = 0;
      var middle = self.pagesEl.scrollTop + self.pagesEl.clientHeight * 0.35;
      for (var i = 0; i < self.pages.length; i++) {
        var p = self.pages[i];
        if (p.el.offsetTop + p.el.offsetHeight > middle) { self.setCurrent(p.number); break; }
      }
      self.hideMenu();
    });
  }

  setCurrent(number) {
    if (number === this.current) return;
    this.current = number;
    if (document.activeElement !== this.pageInput) this.pageInput.value = String(number);
  }

  goToPage(number) {
    if (!this.pages.length || !number) return;
    var target = this.pages[Math.max(1, Math.min(this.pages.length, number)) - 1];
    this.pagesEl.scrollTop = target.el.offsetTop - 12;
    this.setCurrent(target.number);
    this.pageInput.value = String(target.number);
  }

  async extractText() {
    // Extract once per document; the server keeps it for search, summaries and the MCP server.
    var texts = [];
    try {
      for (var n = 1; n <= this.pdf.numPages; n++) {
        var page = await this.pdf.getPage(n);
        var content = await page.getTextContent();
        texts.push(content.items.map(function (item) { return (item.str || "") + (item.hasEOL ? "\n" : " "); }).join("")
          .replace(/[ \t]+\n/g, "\n").replace(/ {2,}/g, " ").trim());
        if (!this.alive) return;
      }
      this.texts = texts;
      if (!this.doc || this.doc.text_pages !== texts.length) {
        await this.app.api.put("/api/documents/" + this.id + "/text", { pages: texts });
        this.app.store.load();
      }
    } catch (error) {
      console.warn("text extraction failed", error);
    }
  }

  // ---- context for the assistant ----
  pageText(number) { return this.texts[(number || this.current) - 1] || ""; }
  paperText(limit) {
    var joined = this.texts.map(function (t, i) { return "[page " + (i + 1) + "]\n" + t; }).join("\n\n");
    return joined.length > limit ? joined.slice(0, limit) + "\n[truncated]" : joined;
  }
  title() { return this.doc ? this.doc.title : ""; }

  // ---- selection menu ----
  selectionInfo() {
    var selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
    var range = selection.getRangeAt(0);
    var node = range.commonAncestorContainer;
    var element = node.nodeType === 1 ? node : node.parentElement;
    if (!element || !this.pagesEl.contains(element)) return null;
    var text = selection.toString().replace(/\s+/g, " ").trim();
    if (text.length < 2) return null;
    var pageEl = element.closest(".page") || (range.startContainer.parentElement && range.startContainer.parentElement.closest(".page"));
    return { text: text, page: pageEl ? Number(pageEl.dataset.page) : this.current, rect: range.getBoundingClientRect() };
  }

  onSelection() {
    clearTimeout(this.selectionTimer);
    var self = this;
    this.selectionTimer = setTimeout(function () {
      var info = self.selectionInfo();
      if (info) self.showMenu(info); else self.hideMenu();
    }, 180);
  }

  showMenu(info) {
    var self = this, app = this.app;
    this.hideMenu();
    this.selection = info;
    function run(task) {
      self.hideMenu();
      app.assistant.runOnSelection(task, info);
    }
    this.menu = h("div", { class: "selection-menu", role: "toolbar" },
      h("button", { onclick: function () { run("translate"); } }, icon("translate"), "번역", h("kbd", null, "T")),
      h("button", { onclick: function () { run("explain"); } }, icon("sparkle"), "설명", h("kbd", null, "E")),
      h("button", { onclick: function () { self.hideMenu(); app.assistant.quote(info); } }, icon("question"), "질문", h("kbd", null, "Q")),
      h("button", { onclick: function () { navigator.clipboard.writeText(info.text); self.hideMenu(); toast("복사했어요"); } }, icon("copy")));
    this.menu.addEventListener("mousedown", function (event) { event.preventDefault(); });
    document.body.append(this.menu);
    var box = this.menu.getBoundingClientRect();
    var top = info.rect.top - box.height - 8;
    if (top < 8) top = info.rect.bottom + 8;
    this.menu.style.top = top + "px";
    this.menu.style.left = Math.max(8, Math.min(innerWidth - box.width - 8, info.rect.left + info.rect.width / 2 - box.width / 2)) + "px";
  }

  hideMenu() {
    if (this.menu) { this.menu.remove(); this.menu = null; }
  }

  onKey(event) {
    if (!this.menu || event.metaKey || event.ctrlKey || event.altKey) return;
    var target = event.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
    var key = event.key.toLowerCase(), info = this.selection;
    if (key === "t") { event.preventDefault(); this.hideMenu(); this.app.assistant.runOnSelection("translate", info); }
    else if (key === "e") { event.preventDefault(); this.hideMenu(); this.app.assistant.runOnSelection("explain", info); }
    else if (key === "q") { event.preventDefault(); this.hideMenu(); this.app.assistant.quote(info); }
    else if (key === "escape") this.hideMenu();
  }
}

