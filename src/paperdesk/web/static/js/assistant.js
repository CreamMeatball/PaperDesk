import { h, icon, iconButton, toast, MOD } from "./ui.js";

var TASK_LABEL = { translate: "번역", explain: "설명", ask: "질문", summarize: "요약" };
var MAX_TURNS = 60;

// Right-hand panel: a per-paper thread of translations, explanations and questions, with a composer.
export class AssistantPanel {
  constructor(root, app) {
    this.root = root;
    this.app = app;
    this.reader = null;
    this.turns = [];
    this.quoted = null;
    var self = this;
    app.settings.addEventListener("change", function () { if (self.reader) self.renderHead(); });
  }

  attach(reader) {
    this.reader = reader;
    this.quoted = null;
    if (!reader) { this.root.replaceChildren(); return; }
    this.turns = this.loadTurns(reader.id);
    this.build();
  }

  storageKey(id) { return "paperdesk-thread:" + id; }
  loadTurns(id) {
    try { return JSON.parse(localStorage.getItem(this.storageKey(id)) || "[]"); } catch (error) { return []; }
  }
  saveTurns() {
    if (!this.reader) return;
    var done = this.turns.filter(function (t) { return t.status !== "pending"; }).slice(-MAX_TURNS);
    try { localStorage.setItem(this.storageKey(this.reader.id), JSON.stringify(done)); } catch (error) {}
  }

  build() {
    var self = this;
    this.head = h("div", { class: "as-head" });
    this.thread = h("div", { class: "thread" });
    this.ctx = h("div", { class: "ctx" });
    this.input = h("textarea", { rows: "2", placeholder: "이 논문에 대해 물어보세요",
      oninput: function () { self.autosize(); self.sendButton.disabled = !self.input.value.trim(); },
      onkeydown: function (event) {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); self.submit(); }
      } });
    this.sendButton = h("button", { class: "send", title: "보내기", disabled: true, onclick: function () { self.submit(); } }, icon("send", 14));
    var quick = h("div", { class: "quick" },
      h("button", { class: "btn small", onclick: function () { self.summarize(); } }, icon("sparkle", 13), "논문 요약"),
      h("button", { class: "btn small", onclick: function () { self.translatePage(); } }, icon("translate", 13), "현재 쪽 번역"));
    this.root.replaceChildren(this.head, this.thread, quick,
      h("div", { class: "composer" }, this.ctx, this.input,
        h("div", { class: "row" }, h("span", { class: "hint" }, "⏎ 보내기 · ⇧⏎ 줄바꿈 · 글을 선택하면 T/E/Q"), this.sendButton)));
    this.renderHead();
    this.renderContext();
    this.renderThread();
  }

  renderHead() {
    var app = this.app, self = this, active = app.settings.active();
    this.head.replaceChildren.apply(this.head, [
      h("h2", null, "AI 도우미"),
      h("button", { class: "provider-pill", title: "AI 연결 바꾸기", onclick: function () { app.router.go("/settings"); } },
        h("i", { class: "dot " + (active ? (active.available ? "ok" : "bad") : "") }),
        h("span", null, active ? active.label : "AI 연결 안 됨")),
      this.turns.length ? iconButton("trash", "대화 지우기", function () { self.turns = []; self.saveTurns(); self.renderThread(); }) : null,
      iconButton("close", "패널 닫기 (" + MOD + "J)", function () { app.toggleAssistant(); })].filter(Boolean));
  }

  renderContext() {
    var self = this;
    if (!this.quoted) { this.ctx.replaceChildren(); this.ctx.style.display = "none"; return; }
    this.ctx.style.display = "";
    this.ctx.replaceChildren(icon("question", 13), h("span", null, "“" + this.quoted.text + "”"),
      iconButton("close", "인용 빼기", function () { self.quoted = null; self.renderContext(); }));
  }

  renderThread() {
    var self = this;
    if (!this.turns.length) {
      this.thread.replaceChildren(h("div", { class: "as-empty" },
        h("b", null, "읽다가 막히는 곳을 물어보세요"),
        "PDF에서 글을 선택하면 번역·설명·질문을 할 수 있어요. 대화는 이 논문마다 따로 저장돼요."));
      return;
    }
    this.thread.replaceChildren.apply(this.thread, this.turns.map(function (turn) { return self.renderTurn(turn); }));
    this.thread.scrollTop = this.thread.scrollHeight;
  }

  renderTurn(turn) {
    var self = this;
    var answer;
    if (turn.status === "pending") answer = h("div", { class: "answer" }, h("span", { class: "typing" }, h("i"), h("i"), h("i")));
    else if (turn.status === "error") {
      answer = h("div", { class: "answer error" }, turn.error,
        turn.code === "provider_unavailable" ? h("div", null, h("button", { class: "btn small", style: "margin-top:6px",
          onclick: function () { self.app.router.go("/settings"); } }, "설정에서 AI 연결하기")) : null);
    } else answer = h("div", { class: "answer" }, turn.answer);
    return h("div", { class: "turn" },
      turn.question ? h("div", { class: "ask" }, turn.question) : null,
      h("div", { class: "task" }, TASK_LABEL[turn.task] || turn.task, turn.page ? "· " + turn.page + "쪽" : null),
      turn.quote ? h("div", { class: "quote" }, turn.quote) : null,
      answer,
      turn.status === "done" ? h("div", { class: "meta" },
        h("span", null, [turn.provider, turn.model].filter(Boolean).join(" · ") + (turn.cached ? " · 저장된 답" : "")),
        h("button", { title: "복사", onclick: function () { navigator.clipboard.writeText(turn.answer); toast("복사했어요"); } }, icon("copy", 13))) : null);
  }

  autosize() {
    this.input.style.height = "auto";
    this.input.style.height = Math.min(160, this.input.scrollHeight) + "px";
  }

  quote(info) {
    if (!info) return;
    this.app.showAssistant();
    this.quoted = info;
    this.renderContext();
    this.input.focus();
  }

  runOnSelection(task, info) {
    if (!info) return;
    this.app.showAssistant();
    this.run({ task: task, text: info.text, context: this.reader.pageText(info.page).slice(0, 6000), quote: info.text, page: info.page });
  }

  submit() {
    var question = this.input.value.trim();
    if (!question || !this.reader) return;
    var quoted = this.quoted;
    this.input.value = "";
    this.autosize();
    this.sendButton.disabled = true;
    this.quoted = null;
    this.renderContext();
    if (quoted) {
      this.run({ task: "ask", text: quoted.text, question: question, context: this.reader.pageText(quoted.page).slice(0, 6000), quote: quoted.text, page: quoted.page });
    } else {
      var page = this.reader.current;
      var text = this.reader.paperText(50000);
      if (!text) { toast("본문을 아직 읽는 중이에요. 잠시 후 다시 물어보세요.", true); return; }
      this.run({ task: "ask", text: text, question: question, page: null });
    }
  }

  summarize() {
    var text = this.reader && this.reader.paperText(55000);
    if (!text) { toast("본문을 아직 읽는 중이에요.", true); return; }
    this.run({ task: "summarize", text: text });
  }

  translatePage() {
    var page = this.reader.current, text = this.reader.pageText(page);
    if (!text) { toast("이 쪽에서 글자를 찾지 못했어요.", true); return; }
    this.run({ task: "translate", text: text, page: page, quote: text.slice(0, 160) + (text.length > 160 ? "…" : "") });
  }

  async run(request) {
    var reader = this.reader, self = this;
    var turn = { task: request.task, question: request.question || "", quote: request.quote || "", page: request.page || null, status: "pending" };
    this.turns.push(turn);
    this.renderThread();
    this.renderHead();
    try {
      var result = await this.app.api.post("/api/assist", {
        task: request.task, text: request.text, question: request.question || "", context: request.context || ""
      });
      turn.status = "done";
      turn.answer = result.text;
      turn.provider = this.providerLabel(result.provider_id);
      turn.model = result.model;
      turn.cached = result.cached;
    } catch (error) {
      turn.status = "error";
      turn.error = error.message;
      turn.code = error.code;
    }
    if (this.reader !== reader) return; // user switched papers while waiting
    this.saveTurns();
    this.renderThread();
  }

  providerLabel(id) {
    var data = this.app.settings.data;
    var found = data && data.providers.find(function (p) { return p.id === id; });
    return found ? found.label : id;
  }
}

