import { pref, setPref } from "./prefs.js";
import { h, icon, iconButton, confirmDialog, showMenu, toast, MOD } from "./ui.js";
import { drawRects, rectContains } from "./textmap.js";
import { t } from "./i18n.js";

export var COLORS = ["yellow", "green", "blue", "pink"];

// Highlights and notes, stored on the server per document. Drawn under the text layer so selection still works.
export class Annotations {
  constructor(reader) {
    this.reader = reader;
    this.app = reader.app;
    this.items = [];
    this.lastColor = pref("highlight_color", "yellow");
    this.listeners = new Set();
    this.onClick = this.onClick.bind(this);
    reader.pagesEl.addEventListener("click", this.onClick);
    reader.pagesEl.addEventListener("contextmenu", this.onClick);
    this.load();
  }

  destroy() {
    this.reader.pagesEl.removeEventListener("click", this.onClick);
    this.reader.pagesEl.removeEventListener("contextmenu", this.onClick);
    if (this.editor) this.editor.close(null);
    this.listeners.clear();
  }

  annotationAt(pageEl, x, y) {
    var box = pageEl.getBoundingClientRect(), px = (x - box.left) / box.width, py = (y - box.top) / box.height;
    var page = Number(pageEl.dataset.page);
    return this.items.find(function (a) { return a.page === page && a.rects.some(function (r) { return rectContains(r, px, py); }); });
  }

  onClick(event) {
    if (this.reader.area.active || !window.getSelection().isCollapsed || event.target.closest("button, .tcol, .layer.over")) return;
    var page = event.target.closest(".page");
    var annotation = page && this.annotationAt(page, event.clientX, event.clientY);
    if (!annotation) return;
    event.preventDefault();
    this.reader.hideMenu();
    var self = this;
    showMenu(event.clientX, event.clientY, [
      { label: annotation.note ? t("메모 고치기") : t("메모 추가"), icon: "note", onClick: function () { self.editNote(annotation); } },
      { label: annotation.note ? t("메모·표시 삭제") : t("하이라이트 지우기"), icon: "trash", danger: true, onClick: async function () {
        if (!annotation.note || await confirmDialog({ title: t("이 표시를 지울까요?"), confirm: t("삭제"), danger: true })) self.remove(annotation);
      } }
    ]);
  }

  async load() {
    try {
      var data = await this.app.api.get("/api/documents/" + this.reader.id + "/annotations");
      this.items = data.annotations;
    } catch (error) { console.warn(error); }
    this.redrawAll();
  }

  onChange(fn) { this.listeners.add(fn); return function () { this.listeners.delete(fn); }.bind(this); }
  changed() { this.listeners.forEach(function (fn) { fn(); }); this.redrawAll(); }

  redrawAll() {
    var self = this;
    this.reader.pages.forEach(function (state) { if (state.rendered) self.onPageRender(state); });
  }

  onPageRender(state) {
    var marks = state.el.querySelector(".layer.marks"), ui = state.el.querySelector(".layer.ui"), self = this;
    marks.replaceChildren();
    ui.querySelectorAll(".note-pin").forEach(function (n) { n.remove(); });
    this.items.filter(function (a) { return a.page === state.number; }).forEach(function (a) {
      drawRects(marks, a.rects, "hl " + a.color);
      if (a.note) {
        var last = a.rects[a.rects.length - 1];
        ui.append(h("button", { class: "note-pin " + a.color, title: a.note, style: "left:calc(" + last[2] * 100 + "% + 2px);top:" + last[1] * 100 + "%",
          onclick: function (event) { self.editNote(a, event.currentTarget.getBoundingClientRect()); } }, icon("note", 12)));
      }
    });
  }

  async create(info, kind, color, note) {
    if (!info.rects || !info.rects.length) { toast(t("이 부분은 표시할 수 없어요."), true); return null; }
    color = color || this.lastColor;
    this.lastColor = color;
    setPref("highlight_color", color);
    try {
      var data = await this.app.api.post("/api/documents/" + this.reader.id + "/annotations",
        { page: info.page, kind: kind, color: color, text: info.text, rects: info.rects, note: note || "" });
      this.items.push(data.annotation);
      this.changed();
      return data.annotation;
    } catch (error) { toast(error.message, true); return null; }
  }

  async createNote(info) {
    var note = await this.noteDialog(t("메모 남기기"), "", info.text, null, info.rect);
    if (note) {
      await this.create(info, "note", this.lastColor, note);
      this.app.assistant.showTab("notes");
    }
  }

  async editNote(a, anchor) {
    if (this.editor && this.editor.key === a.id) {
      this.editor.panel.hidden = !this.editor.panel.hidden;
      if (!this.editor.panel.hidden) this.editor.area.focus();
      return;
    }
    if (!anchor) {
      var state = this.reader.pages[a.page - 1], rect = a.rects[a.rects.length - 1];
      if (state) {
        var page = state.el.getBoundingClientRect();
        anchor = { left: page.left + rect[0] * page.width, right: page.left + rect[2] * page.width, top: page.top + rect[1] * page.height };
      }
    }
    var self = this;
    var note = await this.noteDialog(a.note ? t("메모 고치기") : t("메모 추가"), a.note, a.text, function () { self.remove(a); }, anchor, a.id);
    if (note != null) await this.update(a, { note: note });
  }

  noteDialog(title, value, quote, onDelete, anchor, key) {
    if (this.editor) { this.editor.panel.hidden = false; this.editor.area.focus(); return Promise.resolve(null); }
    var self = this;
    return new Promise(function (resolve) {
      var previous = document.activeElement, finished = false, drag = null;
      var area = h("textarea", { class: "note-input", "aria-label": t("메모 내용"), placeholder: t("생각, 질문, 다시 볼 이유…") });
      area.value = value || "";
      var panel = h("div", { class: "floating-note", role: "dialog", "aria-modal": "false", "aria-label": title });
      function done(v) {
        if (finished) return;
        finished = true;
        window.removeEventListener("resize", keepVisible);
        panel.remove();
        self.editor = null;
        if (previous && previous.isConnected) previous.focus({ preventScroll: true });
        resolve(v);
      }
      function move(left, top) {
        panel.style.left = Math.max(8, Math.min(innerWidth - panel.offsetWidth - 8, left)) + "px";
        panel.style.top = Math.max(8, Math.min(innerHeight - panel.offsetHeight - 8, top)) + "px";
        panel.style.right = panel.style.bottom = "auto";
      }
      function keepVisible() { var r = panel.getBoundingClientRect(); move(r.left, r.top); }
      var header = h("div", { class: "floating-note-head" }, icon("note", 16), h("h3", null, title),
        iconButton("close", t("닫기"), function () { done(null); }));
      header.addEventListener("pointerdown", function (event) {
        if (event.button !== 0 || event.target.closest("button")) return;
        var rect = panel.getBoundingClientRect();
        drag = { x: event.clientX - rect.left, y: event.clientY - rect.top };
        header.setPointerCapture(event.pointerId);
        event.preventDefault();
      });
      header.addEventListener("pointermove", function (event) { if (drag) move(event.clientX - drag.x, event.clientY - drag.y); });
      header.addEventListener("pointerup", function () { drag = null; });
      header.addEventListener("pointercancel", function () { drag = null; });
      area.addEventListener("keydown", function (event) {
        if (event.isComposing || event.keyCode === 229) return;
        if ((event.key === "Enter" && (event.metaKey || event.ctrlKey)) || event.key === "Escape") {
          event.preventDefault(); event.stopPropagation();
          done(event.key === "Escape" ? null : area.value.trim());
        }
      });
      panel.append(header, quote ? h("blockquote", { class: "floating-note-quote" }, quote) : null, area,
        h("div", { class: "floating-note-actions" },
          onDelete ? h("button", { class: "btn danger", onclick: function () { done(null); onDelete(); } }, t("삭제")) : null,
          h("span", { class: "hint" }, MOD + "⏎ " + t("저장")),
          h("button", { class: "btn", onclick: function () { done(null); } }, t("취소")),
          h("button", { class: "btn primary", onclick: function () { done(area.value.trim()); } }, t("저장"))));
      self.editor = { area: area, panel: panel, key: key, close: done };
      document.body.append(panel);
      if (anchor) {
        var left = anchor.right + 12;
        if (left + panel.offsetWidth > innerWidth - 8) left = anchor.left - panel.offsetWidth - 12;
        if (left < 8) left = anchor.left;
        move(left, anchor.top);
      }
      window.addEventListener("resize", keepVisible);
      area.focus();
    });
  }

  async update(a, changes) {
    try {
      var data = await this.app.api.patch("/api/annotations/" + a.id, changes);
      Object.assign(a, data.annotation);
      this.changed();
    } catch (error) { toast(error.message, true); }
  }

  async remove(a) {
    try {
      await this.app.api.del("/api/annotations/" + a.id);
      this.items = this.items.filter(function (x) { return x.id !== a.id; });
      this.changed();
    } catch (error) { toast(error.message, true); }
  }

  // List for the assistant panel's 메모 tab.
  renderList(container) {
    var self = this, reader = this.reader;
    if (!this.items.length) {
      container.replaceChildren(h("div", { class: "as-empty" }, h("b", null, t("하이라이트와 메모가 여기에 모여요")),
        t("PDF에서 글을 선택하고 색을 고르거나(H) 메모(C)를 남겨 보세요.")));
      return;
    }
    container.replaceChildren.apply(container, this.items.slice().sort(function (a, b) { return a.page - b.page || a.rects[0][1] - b.rects[0][1]; }).map(function (a) {
      return h("div", { class: "note-item " + a.color },
        h("div", { class: "note-head" }, h("button", { class: "link-btn", onclick: function () { reader.flashRect(a.page, a.rects[0], true); } }, t("{n}쪽", { n: a.page })),
          h("span", { class: "spacer" }),
          h("span", { class: "swatches" }, COLORS.map(function (c) {
            return h("button", { class: "swatch " + c + (c === a.color ? " on" : ""), title: t("색 바꾸기"), onclick: function () { self.update(a, { color: c }); } });
          })),
          iconButton("note", a.note ? t("메모 고치기") : t("메모 추가"), function () { self.editNote(a); }),
          iconButton("trash", t("삭제"), async function () {
            if (await confirmDialog({ title: t("이 표시를 지울까요?"), confirm: t("삭제"), danger: true })) self.remove(a);
          })),
        h("div", { class: "note-quote" }, a.text),
        a.note ? h("div", { class: "note-body" }, a.note) : null);
    }));
  }
}
