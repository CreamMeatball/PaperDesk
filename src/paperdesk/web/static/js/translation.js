import { confirmDialog, h, icon, menuAt, toast } from "./ui.js";
import { compact } from "./layout.js";
import { renderInlineMath } from "./markdown.js";
import { drawRects, rectContains } from "./textmap.js";

var BATCH_BLOCKS = 10, BATCH_CHARS = 5000;
var MODES = [["side", "나란히"], ["over", "원문 위에"], ["off", "번역 숨기기"]];
var XREF = /(그림|표|알고리즘|Figures?|Figs?\.|Tables?|Tabs?\.|Algorithms?|Alg\.)\s*(\d+|[A-Z]\.\d+)|(식|수식|Eqs?\.|Equations?)\s*\(?(\d+)\)?|\[(\d{1,4}(?:\s*[,–\-]\s*\d{1,4})*)\]/g;

// Body translation: cards beside (or over) the PDF, sentence-to-sentence linking, magnifier per paragraph,
// section and whole-paper translation through a queue.
export class TranslationController {
  constructor(reader) {
    this.reader = reader;
    this.app = reader.app;
    this.store = {};
    this.pending = new Set();
    this.queue = [];
    this.running = false;
    this.done = 0;
    this.total = 0;
    this.active = null;
    var self = this;
    this.label = h("span", null, "번역");
    this.button = h("button", { class: "btn tb-btn", title: "본문 번역", onclick: function (event) { self.openMenu(event.currentTarget); } },
      icon("translate"), this.label, icon("chevronDown", 12));
    this.hover = h("div", { class: "block-hover" });
    this.hoverButton = h("button", { class: "block-btn", onmousedown: function (event) { event.preventDefault(); }, onclick: function (event) {
      event.stopPropagation();
      self.onHoverButton();
    } });
    this.hover.append(this.hoverButton);
    this.onMove = this.onMove.bind(this);
    reader.pagesEl.addEventListener("mousemove", this.onMove);
    reader.pagesEl.addEventListener("mouseleave", function () { self.clearSentence(); self.scheduleHideHover(); });
    reader.pagesEl.addEventListener("mouseover", function (event) { self.onCardOver(event); });
    reader.pagesEl.addEventListener("mouseout", function (event) { self.onCardOut(event); });
  }

  destroy() { this.queue = []; this.hover.remove(); }

  get analysis() { return this.reader.analysis; }

  async onAnalysis() {
    try {
      var data = await this.app.api.get("/api/documents/" + this.reader.id + "/translations");
      this.language = data.language;
      this.store = data.blocks || {};
    } catch (error) { console.warn(error); }
    this.updateLabel();
    var reader = this.reader, self = this;
    reader.pages.forEach(function (state) { if (state.rendered) self.renderPage(state); });
    reader.nav.refreshSections();
  }

  blocksOn(page) {
    var info = this.analysis && this.analysis.pages[page - 1];
    return info ? info.blocks.filter(function (b) { return b.translatable; }) : [];
  }

  // ---------- menu ----------
  openMenu(anchor) {
    var self = this, reader = this.reader, ready = !!this.analysis;
    var all = ready ? this.analysis.blocks.filter(function (b) { return b.translatable && !self.store[b.key]; }) : [];
    var items = [{ title: "번역 보기" }];
    MODES.forEach(function (mode) {
      items.push({ label: (reader.tmode === mode[0] ? "✓ " : "   ") + mode[1], onClick: function () { reader.setTranslationMode(mode[0]); } });
    });
    items.push("-");
    if (!ready) items.push({ title: "문서를 분석하는 중이에요…" });
    else {
      items.push({ label: "현재 쪽 번역", icon: "file", onClick: function () { self.translatePage(reader.current); } });
      items.push({ label: "목차에서 골라 번역…", icon: "list", onClick: function () { reader.nav.open("sections"); } });
      items.push({ label: all.length ? "남은 본문 전체 번역 (" + all.length + "문단)" : "전체 번역 완료", icon: "translate",
        onClick: function () { if (all.length) self.translateAll(all); } });
      if (this.running) items.push({ label: "번역 멈추기", icon: "close", onClick: function () { self.queue = []; toast("남은 번역을 취소했어요"); } });
    }
    menuAt(anchor, items);
  }

  updateLabel() {
    if (this.running || this.queue.length) this.label.textContent = "번역 " + this.done + "/" + this.total;
    else {
      var count = Object.keys(this.store).length;
      this.label.textContent = count ? "번역 " + count : "번역";
    }
    this.button.classList.toggle("busy", this.running);
  }

  // ---------- queue ----------
  translatePage(page) {
    var blocks = this.blocksOn(page);
    if (!blocks.length) { toast("이 쪽에는 번역할 본문이 없어요."); return; }
    this.enqueue(blocks);
  }

  translateSection(sectionId) {
    var blocks = this.analysis.blocks.filter(function (b) { return b.translatable && b.sectionId === sectionId; });
    this.enqueue(blocks);
  }

  async translateAll(blocks) {
    var chars = blocks.reduce(function (n, b) { return n + b.text.length; }, 0);
    var ok = await confirmDialog({ title: "남은 본문을 모두 번역할까요?", confirm: "번역 시작",
      message: blocks.length + "문단, 약 " + Math.round(chars / 1000) + "천 자예요. 연결한 AI의 사용량이나 요금이 그만큼 쓰여요. 이미 번역한 문단은 다시 보내지 않아요." });
    if (ok) this.enqueue(blocks);
  }

  enqueue(blocks) {
    var self = this;
    if (this.reader.tmode === "off") this.reader.setTranslationMode("side");
    var fresh = blocks.filter(function (b) { return !self.store[b.key] && !self.pending.has(b.key); });
    if (!fresh.length) { toast("이미 번역했어요."); return; }
    fresh.forEach(function (b) { self.pending.add(b.key); });
    var batch = [], size = 0;
    fresh.forEach(function (b) {
      if (batch.length && (batch.length >= BATCH_BLOCKS || size + b.text.length > BATCH_CHARS || batch[0].sectionId !== b.sectionId)) {
        self.queue.push(batch); batch = []; size = 0;
      }
      batch.push(b); size += b.text.length;
    });
    if (batch.length) this.queue.push(batch);
    this.total += fresh.length;
    this.refreshPages(fresh);
    this.updateLabel();
    this.run();
  }

  async run() {
    if (this.running) return;
    this.running = true;
    this.updateLabel();
    while (this.queue.length && this.reader.alive) {
      var batch = this.queue.shift(), self = this;
      var section = this.analysis.sections.find(function (s) { return s.id === batch[0].sectionId; });
      try {
        var result = await this.app.api.post("/api/documents/" + this.reader.id + "/translations", {
          blocks: batch.map(function (b) { return { key: b.key, sentences: b.sentences }; }),
          title: this.reader.title(), section: section ? section.title : "", terms: this.app.assistant.keyTerms()
        });
        Object.assign(this.store, result.blocks);
        if (result.missing && result.missing.length) toast(result.missing.length + "문단은 번역 결과를 받지 못했어요. 다시 시도해 주세요.", true);
      } catch (error) {
        toast(error.message, true);
        if (error.code === "provider_unavailable") { this.queue.forEach(function (b) { b.forEach(function (x) { self.pending.delete(x.key); }); }); this.queue = []; }
      }
      batch.forEach(function (b) { self.pending.delete(b.key); });
      this.done += batch.length;
      this.refreshPages(batch);
      this.updateLabel();
      this.reader.nav.refreshSections();
    }
    this.running = false;
    this.done = 0;
    this.total = 0;
    this.queue.forEach(function (batch) { batch.forEach(function (b) { this.pending.delete(b.key); }, this); }, this);
    this.updateLabel();
  }

  refreshPages(blocks) {
    var reader = this.reader, pages = new Set(blocks.map(function (b) { return b.page; }));
    pages.forEach(function (n) { var state = reader.pages[n - 1]; if (state && state.rendered) reader.translation.renderPage(state); });
  }

  // ---------- cards ----------
  onPageRender(state) { this.renderPage(state); }

  renderPage(state) {
    var mode = this.reader.tmode, self = this;
    var over = state.el.querySelector(".layer.over");
    state.tcol.replaceChildren();
    over.replaceChildren();
    if (mode === "off" || !this.analysis) return;
    var blocks = this.blocksOn(state.number).filter(function (b) { return self.store[b.key] || self.pending.has(b.key); });
    var height = state.el.offsetHeight, width = state.el.offsetWidth;
    if (mode === "side") {
      var placed = blocks.slice().sort(function (a, b) { return a.rect[1] - b.rect[1] || a.rect[0] - b.rect[0]; }), bottom = 0;
      placed.forEach(function (block) {
        var card = self.card(block);
        state.tcol.append(card);
        var top = Math.max(block.rect[1] * height, bottom + 6);
        card.style.top = top + "px";
        bottom = top + card.offsetHeight;
      });
      state.tcol.style.minHeight = Math.max(height, bottom + 12) + "px";
    } else {
      blocks.forEach(function (block) {
        var card = self.card(block), r = block.rect;
        card.classList.add("over");
        card.style.cssText = "left:" + r[0] * width + "px;top:" + r[1] * height + "px;width:" + (r[2] - r[0]) * width + "px;height:" + Math.max(14, (r[3] - r[1]) * height) + "px";
        over.append(card);
        var size = Math.max(8, block.size * self.reader.scale * 0.92);
        card.style.fontSize = size + "px";
        for (var i = 0; i < 10 && card.scrollHeight > card.clientHeight + 1 && size > 6; i++) {
          size *= 0.92;
          card.style.fontSize = size + "px";
        }
      });
    }
  }

  card(block) {
    var entry = this.store[block.key], self = this;
    var card = h("div", { class: "tcard kind-" + block.kind, "data-key": block.key });
    if (!entry) {
      card.append(h("div", { class: "pending" }, h("span", { class: "typing" }, h("i"), h("i"), h("i")), " 번역 중"));
      return card;
    }
    var body = h("div", { class: "ttext" });
    if (entry.sentences && entry.sentences.length === block.sentences.length) {
      entry.sentences.forEach(function (sentence, index) {
        body.append(self.linkify(h("span", { class: "tsent", "data-s": String(index) }), sentence), " ");
      });
    } else {
      body.append(this.linkify(h("span", { class: "tsent whole", "data-s": "all" }), entry.text));
    }
    card.append(body);
    return card;
  }

  // Wrap figure/table/equation/citation mentions so hovering them opens the same previews as in the PDF.
  linkify(span, text) {
    var self = this;
    span.append(renderInlineMath(text, function (part) { return self.linkText(part); }));
    return span;
  }

  linkText(text) {
    var span = document.createDocumentFragment(), last = 0, match;
    XREF.lastIndex = 0;
    while ((match = XREF.exec(text))) {
      span.append(text.slice(last, match.index));
      var ref = h("span", { class: "xref" }, match[0]);
      if (match[1]) { ref.dataset.kind = /^(표|Tab)/i.test(match[1]) ? "table" : /^(알고리즘|Alg)/i.test(match[1]) ? "algorithm" : "figure"; ref.dataset.label = match[2]; }
      else if (match[3]) { ref.dataset.kind = "equation"; ref.dataset.label = match[4]; }
      else { ref.dataset.kind = "cite"; ref.dataset.label = match[5]; }
      span.append(ref);
      last = match.index + match[0].length;
    }
    span.append(text.slice(last));
    return span;
  }

  // ---------- sentence linking ----------
  blockFor(key) {
    return this.analysis ? this.analysis.blocks.find(function (b) { return b.key === key; }) : null;
  }

  sentenceRange(block, index) {
    if (index === "all") return [0, compact(block.text).length];
    var start = 0;
    for (var i = 0; i < index; i++) start += compact(block.sentences[i]).length;
    return [start, start + compact(block.sentences[index]).length];
  }

  showSentence(block, index) {
    var state = this.reader.pages[block.page - 1];
    if (!state || !state.map) return;
    this.clearSentence();
    var range = this.sentenceRange(block, index);
    var layer = state.el.querySelector(".layer.flash");
    this.activeRects = drawRects(layer, state.map.blockRects(block, range[0], range[1]), "sent-hl");
    var selector = '.tcard[data-key="' + block.key + '"] .tsent[data-s="' + index + '"]';
    this.activeSpans = Array.prototype.slice.call(this.reader.pagesEl.querySelectorAll(selector));
    this.activeSpans.forEach(function (s) { s.classList.add("active"); });
    this.active = block.key + "#" + index;
  }

  clearSentence() {
    (this.activeRects || []).forEach(function (n) { n.remove(); });
    (this.activeSpans || []).forEach(function (s) { s.classList.remove("active"); });
    this.activeRects = null;
    this.activeSpans = null;
    this.active = null;
  }

  onCardOver(event) {
    var span = event.target.closest && event.target.closest(".tsent");
    if (span && !event.target.closest(".xref")) {
      var card = span.closest(".tcard"), block = this.blockFor(card.dataset.key);
      var index = span.dataset.s === "all" ? "all" : Number(span.dataset.s);
      if (block && this.active !== block.key + "#" + index) this.showSentence(block, index);
    }
    var ref = event.target.closest && event.target.closest(".xref");
    if (ref) this.reader.citations.showForElement(ref, this.resolveRef(ref));
  }

  onCardOut(event) {
    var ref = event.target.closest && event.target.closest(".xref");
    if (ref && !(event.relatedTarget && ref.contains(event.relatedTarget))) this.reader.citations.scheduleHide();
    var span = event.target.closest && event.target.closest(".tsent");
    if (span && !(event.relatedTarget && span.contains(event.relatedTarget))) this.clearSentence();
  }

  resolveRef(ref) {
    var kind = ref.dataset.kind, label = ref.dataset.label, reader = this.reader;
    if (kind === "cite") {
      if (!reader.references || !reader.references.ready) return null;
      var numbers = [];
      label.split(/\s*,\s*/).forEach(function (part) {
        var r = part.split(/\s*[–\-]\s*/).map(Number);
        if (r.length === 2 && r[1] >= r[0] && r[1] - r[0] < 30) for (var n = r[0]; n <= r[1]; n++) numbers.push(n); else numbers.push(r[0]);
      });
      var entries = numbers.map(function (n) { return reader.references.byNumber.get(n); }).filter(Boolean);
      return entries.length ? { kind: "cite", entries: entries, label: "[" + label + "]" } : null;
    }
    var target = reader.visuals.find(kind, label);
    return target ? { kind: "visual", target: target, label: ref.textContent } : null;
  }

  // ---------- hover on the PDF: sentence link + magnifier ----------
  onMove(event) {
    if (event.buttons || !this.analysis || this.reader.area.active) return;
    var pageEl = event.target.closest && event.target.closest(".page");
    if (!pageEl || event.target.closest(".layer.over, .block-hover")) {
      if (!event.target.closest || !event.target.closest(".block-hover")) this.scheduleHideHover();
      return;
    }
    var x = event.clientX, y = event.clientY, self = this;
    if (this.frame) return;
    this.frame = requestAnimationFrame(function () {
      self.frame = 0;
      var state = self.reader.pages[Number(pageEl.dataset.page) - 1];
      if (!state || !state.map) return;
      var box = pageEl.getBoundingClientRect(), px = (x - box.left) / box.width, py = (y - box.top) / box.height;
      var blocks = self.blocksOn(state.number);
      var block = blocks.find(function (b) { return rectContains(b.rect, px, py, 34 / box.width, 2 / box.height); });
      if (block) self.showHover(state, block); else self.scheduleHideHover();
      // sentence under the pointer, for translated blocks
      var index = state.map.hitTest(x, y);
      if (index < 0 || !block || !self.store[block.key] || self.reader.tmode === "off") {
        if (self.active && !self.activeFromCard) self.clearSentence();
        return;
      }
      var offset = state.map.blockOffsetOf(block, index);
      if (offset < 0) return;
      var entry = self.store[block.key], which = "all";
      if (entry.sentences && entry.sentences.length === block.sentences.length) {
        var start = 0;
        for (var i = 0; i < block.sentences.length; i++) {
          var len = compact(block.sentences[i]).length;
          if (offset < start + len) { which = i; break; }
          start += len;
        }
      }
      if (self.active !== block.key + "#" + which) self.showSentence(block, which);
    });
  }

  showHover(state, block) {
    clearTimeout(this.hideTimer);
    var layer = state.el.querySelector(".layer.ui");
    if (this.hover.parentNode !== layer) layer.append(this.hover);
    var r = block.rect;
    this.hover.style.cssText = "left:" + r[0] * 100 + "%;top:" + r[1] * 100 + "%;width:" + (r[2] - r[0]) * 100 + "%;height:" + (r[3] - r[1]) * 100 + "%";
    this.hoverBlock = block;
    var translated = !!this.store[block.key], pending = this.pending.has(block.key);
    var heading = block.kind === "heading";
    this.hoverButton.replaceChildren(pending ? "…" : translated ? icon("check", 13) : heading ? "文" : icon("search", 13));
    this.hoverButton.title = pending ? "번역 중" : translated ? "번역 보기" : heading ? "이 절 번역" : "이 문단 번역";
    this.hoverButton.classList.toggle("done", translated);
    this.hoverButton.classList.toggle("section", heading && !translated);
    this.hover.classList.add("show");
  }

  scheduleHideHover() {
    clearTimeout(this.hideTimer);
    var self = this;
    this.hideTimer = setTimeout(function () { self.hover.classList.remove("show"); self.hoverBlock = null; }, 260);
  }

  onHoverButton() {
    var block = this.hoverBlock;
    if (!block || this.pending.has(block.key)) return;
    if (this.store[block.key]) {
      if (this.reader.tmode === "off") this.reader.setTranslationMode("side");
      var card = this.reader.pagesEl.querySelector('.tcard[data-key="' + block.key + '"]');
      if (card) {
        card.scrollIntoView({ block: "nearest", behavior: "smooth" });
        card.classList.remove("flash"); void card.offsetWidth; card.classList.add("flash");
      }
      return;
    }
    if (block.kind === "heading") this.translateSection(block.sectionId);
    else this.enqueue([block]);
  }
}

