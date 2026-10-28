import { h, icon, iconButton, confirmDialog, toast } from "./ui.js";
import { drawRects } from "./textmap.js";

export var COLORS = ["yellow", "green", "blue", "pink"];

// Highlights and notes, stored on the server per document. Drawn under the text layer so selection still works.
export class Annotations {
  constructor(reader) {
    this.reader = reader;
    this.app = reader.app;
    this.items = [];
    this.lastColor = localStorage.getItem("paperdesk-hl") || "yellow";
    this.listeners = new Set();
    this.load();
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
          onclick: function () { self.editNote(a); } }, icon("note", 12)));
      }
    });
  }

  async create(info, kind, color, note) {
    if (!info.rects || !info.rects.length) { toast("이 부분은 표시할 수 없어요.", true); return null; }
    color = color || this.lastColor;
    this.lastColor = color;
    localStorage.setItem("paperdesk-hl", color);
    try {
      var data = await this.app.api.post("/api/documents/" + this.reader.id + "/annotations",
        { page: info.page, kind: kind, color: color, text: info.text, rects: info.rects, note: note || "" });
      this.items.push(data.annotation);
      this.changed();
      return data.annotation;
    } catch (error) { toast(error.message, true); return null; }
  }

  async createNote(info) {
    var note = await this.noteDialog("메모 남기기", "", info.text);
    if (note) {
      await this.create(info, "note", this.lastColor, note);
      this.app.assistant.showTab("notes");
    }
  }

  async editNote(a) {
    var note = await this.noteDialog("메모 고치기", a.note, a.text, function () { self.remove(a); });
    var self = this;
    if (note != null) await this.update(a, { note: note });
  }

  noteDialog(title, value, quote, onDelete) {
    return new Promise(function (resolve) {
      var area = h("textarea", { class: "text note-input", rows: "5", placeholder: "생각, 질문, 다시 볼 이유…" });
      area.value = value || "";
      var backdrop = h("div", { class: "backdrop" });
      function done(v) { backdrop.remove(); resolve(v); }
      backdrop.addEventListener("mousedown", function (e) { if (e.target === backdrop) done(null); });
      area.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) done(area.value.trim());
        if (e.key === "Escape") done(null);
      });
      backdrop.append(h("div", { class: "dialog wide" }, h("h3", null, title),
        quote ? h("p", { class: "quote" }, quote.length > 220 ? quote.slice(0, 220) + "…" : quote) : null, area,
        h("div", { class: "buttons" },
          onDelete ? h("button", { class: "btn danger", style: "margin-right:auto", onclick: function () { done(null); onDelete(); } }, "삭제") : null,
          h("button", { class: "btn", onclick: function () { done(null); } }, "취소"),
          h("button", { class: "btn primary", onclick: function () { done(area.value.trim()); } }, "저장"))));
      document.body.append(backdrop);
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
      container.replaceChildren(h("div", { class: "as-empty" }, h("b", null, "하이라이트와 메모가 여기에 모여요"),
        "PDF에서 글을 선택하고 색을 고르거나(H) 메모(C)를 남겨 보세요."));
      return;
    }
    container.replaceChildren.apply(container, this.items.slice().sort(function (a, b) { return a.page - b.page || a.rects[0][1] - b.rects[0][1]; }).map(function (a) {
      return h("div", { class: "note-item " + a.color },
        h("div", { class: "note-head" }, h("button", { class: "link-btn", onclick: function () { reader.flashRect(a.page, a.rects[0], true); } }, a.page + "쪽"),
          h("span", { class: "spacer" }),
          h("span", { class: "swatches" }, COLORS.map(function (c) {
            return h("button", { class: "swatch " + c + (c === a.color ? " on" : ""), title: "색 바꾸기", onclick: function () { self.update(a, { color: c }); } });
          })),
          iconButton("note", a.note ? "메모 고치기" : "메모 추가", function () { self.editNote(a); }),
          iconButton("trash", "삭제", async function () {
            if (await confirmDialog({ title: "이 표시를 지울까요?", confirm: "삭제", danger: true })) self.remove(a);
          })),
        h("div", { class: "note-quote" }, a.text),
        a.note ? h("div", { class: "note-body" }, a.note) : null);
    }));
  }
}

