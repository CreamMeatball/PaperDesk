import { pref, setPref } from "./prefs.js";
import { h, icon, iconButton } from "./ui.js";
import { t } from "./i18n.js";

// Left drawer inside the reader: table of contents (with section translation) and page thumbnails.
export class Navigator {
  constructor(reader) {
    this.reader = reader;
    this.tab = pref("navigator_tab", "sections");
    this.selected = new Set();
    var self = this;
    this.button = iconButton("list", t("목차·쪽 목록"), function () { self.toggle(); });
    this.drawer = h("aside", { class: "nav-drawer", hidden: true });
    reader.bodyEl.prepend(this.drawer);
    if (pref("navigator") === "open") this.open(this.tab, true);
  }

  toggle() { if (this.drawer.hidden) this.open(this.tab); else this.close(); }

  open(tab, quiet) {
    this.tab = tab || this.tab;
    setPref("navigator_tab", this.tab);
    setPref("navigator", "open");
    var wasHidden = this.drawer.hidden;
    this.drawer.hidden = false;
    this.button.classList.add("on");
    this.render();
    if (wasHidden && !quiet) this.reader.onResize();
  }

  close() {
    this.drawer.hidden = true;
    this.button.classList.remove("on");
    setPref("navigator", "closed");
    if (this.thumbObserver) this.thumbObserver.disconnect();
    this.reader.onResize();
  }

  onAnalysis() { if (!this.drawer.hidden) this.render(); }
  onPagesBuilt() { if (!this.drawer.hidden && this.tab === "pages") this.render(); }
  onCurrentPage(number) {
    this.drawer.querySelectorAll(".thumb.current, .toc-row.current").forEach(function (n) { n.classList.remove("current"); });
    var thumb = this.drawer.querySelector('.thumb[data-page="' + number + '"]');
    if (thumb) { thumb.classList.add("current"); if (!this.drawer.hidden && this.tab === "pages") thumb.scrollIntoView({ block: "nearest" }); }
  }
  refreshSections() { if (!this.drawer.hidden && this.tab === "sections") this.render(); }

  render() {
    var self = this;
    var tabs = h("div", { class: "seg nav-tabs" },
      h("button", { class: this.tab === "sections" ? "on" : "", onclick: function () { self.open("sections"); } }, t("목차")),
      h("button", { class: this.tab === "pages" ? "on" : "", onclick: function () { self.open("pages"); } }, t("쪽")));
    var body = h("div", { class: "nav-body" });
    this.drawer.replaceChildren(h("div", { class: "nav-head" }, tabs, iconButton("close", t("닫기"), function () { self.close(); })), body);
    if (this.tab === "pages") this.renderPages(body); else this.renderSections(body);
  }

  renderSections(body) {
    var reader = this.reader, analysis = reader.analysis, self = this;
    if (!analysis) { body.append(h("div", { class: "loading" }, t("목차를 만드는 중…"))); return; }
    var store = reader.translation.store;
    var rows = analysis.sections.map(function (section) {
      var blocks = analysis.blocks.filter(function (b) { return b.sectionId === section.id && b.translatable; });
      var done = blocks.filter(function (b) { return store[b.key]; }).length;
      var box = h("input", { type: "checkbox", checked: self.selected.has(section.id), disabled: !blocks.length || done === blocks.length,
        onchange: function () { if (box.checked) self.selected.add(section.id); else self.selected.delete(section.id); updateButton(); } });
      return h("div", { class: "toc-row level-" + Math.min(section.level, 3) + (section.references ? " refs" : "") },
        section.references ? h("span", { class: "toc-box" }) : box,
        h("button", { class: "toc-title", title: t(section.title), onclick: function () { reader.goToPage(section.page, section.top || 0); } }, t(section.title)),
        blocks.length ? h("span", { class: "toc-state" + (done === blocks.length ? " done" : "") }, done === blocks.length ? "✓" : done ? done + "/" + blocks.length : "") : null);
    });
    var translate = h("button", { class: "btn primary small", onclick: function () {
      var picked = analysis.blocks.filter(function (b) { return b.translatable && self.selected.has(b.sectionId); });
      self.selected.clear();
      reader.translation.enqueue(picked);
      self.render();
    } });
    function updateButton() {
      var count = analysis.blocks.filter(function (b) { return b.translatable && self.selected.has(b.sectionId) && !store[b.key]; }).length;
      translate.textContent = count ? t("선택한 절 번역 ({n}문단)", { n: count }) : t("번역할 절을 고르세요");
      translate.disabled = !count;
    }
    updateButton();
    body.append(h("div", { class: "toc" }, rows), h("div", { class: "nav-foot" }, translate));
  }

  renderPages(body) {
    var reader = this.reader, self = this;
    if (this.thumbObserver) this.thumbObserver.disconnect();
    if (!reader.pages.length) { body.append(h("div", { class: "loading" }, t("불러오는 중…"))); return; }
    var list = h("div", { class: "thumbs" });
    this.thumbObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { self.drawThumb(entry.target); self.thumbObserver.unobserve(entry.target); }
      });
    }, { root: body, rootMargin: "300px 0px" });
    reader.pages.forEach(function (state) {
      var ratio = state.size.height / state.size.width;
      var thumb = h("button", { class: "thumb" + (state.number === reader.current ? " current" : ""), "data-page": String(state.number),
        onclick: function () { reader.goToPage(state.number); } },
        h("div", { class: "thumb-page", style: "aspect-ratio:" + (1 / ratio) }), h("span", null, String(state.number)));
      list.append(thumb);
      self.thumbObserver.observe(thumb);
    });
    body.append(list);
  }

  async drawThumb(thumb) {
    var reader = this.reader, number = Number(thumb.dataset.page);
    try {
      var page = await reader.pdf.getPage(number);
      var base = page.getViewport({ scale: 1 }), scale = 300 / base.width;
      var viewport = page.getViewport({ scale: scale });
      var canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      await page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport }).promise;
      thumb.querySelector(".thumb-page").replaceChildren(canvas);
    } catch (error) { console.warn(error); }
  }
}
