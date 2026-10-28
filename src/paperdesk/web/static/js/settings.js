import { h, icon, iconButton, toast } from "./ui.js";

var KIND_LABEL = {
  "local-cli": "내 컴퓨터 CLI", "account": "계정 로그인", "api": "API 키", "local-server": "로컬·자체 서버", "offline": "체험"
};
var THEMES = [["system", "시스템 연동"], ["dark", "다크"], ["light", "라이트"]];

export class SettingsView {
  constructor(root, app, route) {
    this.root = root;
    this.app = app;
    this.open = new Set();
    this.results = {};
    this.render(true);
  }

  async render(reload) {
    var self = this, app = this.app;
    var toolbar = h("div", { class: "toolbar" },
      app.sidebarHidden() ? iconButton("sidebar", "사이드바 보이기", function () { app.toggleSidebar(); }) : null,
      iconButton("back", "뒤로", function () { history.length > 1 ? history.back() : app.router.go("/library"); }),
      h("h1", null, "설정"));
    this.inner = h("div", { class: "settings-inner" });
    this.root.replaceChildren(toolbar, h("div", { class: "settings" }, this.inner));
    if (reload || !app.settings.data) {
      this.inner.append(h("div", { class: "loading" }, "AI 연결 상태를 확인하는 중…"));
      try { await app.settings.load(); } catch (error) { toast(error.message, true); return; }
    }
    var data = app.settings.data;
    if (!this.open.size && data.provider) this.open.add(data.provider);
    var health = null;
    try { health = await app.api.get("/api/health"); } catch (error) { health = null; }
    this.inner.replaceChildren(
      h("h2", null, "설정"),
      h("p", { class: "lead" }, "모든 논문과 설정은 이 컴퓨터에만 저장돼요. API 키는 macOS 키체인에 보관해요."),
      this.general(data),
      h("h3", null, "AI 연결"),
      h("p", { class: "lead" }, "번역·설명·질문에 쓸 AI를 하나 고르세요. 이미 쓰는 계정이나 내 컴퓨터의 모델을 그대로 연결할 수 있어요."),
      h("div", { class: "group" }, data.providers.map(function (p) { return self.providerCard(p, data.provider); })),
      h("h3", null, "Claude 데스크톱·Codex에서 내 논문 읽기"),
      this.mcpSection(),
      h("h3", null, "정보"),
      h("div", { class: "group" }, h("div", { class: "field-row" }, h("div", { class: "k" }, "버전"), h("span", null, health ? health.version : "—"))));
  }

  general(data) {
    var app = this.app, self = this;
    var choice = window.paperdeskTheme.get();
    var seg = h("div", { class: "seg", role: "radiogroup" }, THEMES.map(function (item) {
      return h("button", { class: choice === item[0] ? "on" : "", role: "radio", "aria-checked": String(choice === item[0]),
        onclick: function () { window.paperdeskTheme.set(item[0]); app.themeChanged(); self.render(false); } }, item[1]);
    }));
    var languages = data.languages.indexOf(data.target_language) >= 0 ? data.languages : [data.target_language].concat(data.languages);
    var select = h("select", { onchange: async function () {
      try { await app.api.put("/api/settings", { target_language: select.value }); await app.settings.load(); toast("번역 언어를 바꿨어요"); }
      catch (error) { toast(error.message, true); }
    } }, languages.map(function (lang) { return h("option", { value: lang, selected: lang === data.target_language }, lang); }));
    return h("div", { class: "group" },
      h("div", { class: "field-row" }, h("div", { class: "k" }, "화면 테마", h("small", null, "PDF 지면은 어느 테마에서나 흰색으로 보여요.")), seg),
      h("div", { class: "field-row" }, h("div", { class: "k" }, "번역·답변 언어", h("small", null, "처음에는 시스템 언어를 따라요.")), select));
  }

  providerCard(p, activeId) {
    var self = this, app = this.app;
    var isOpen = this.open.has(p.id);
    var radio = h("input", { type: "radio", name: "provider", checked: p.id === activeId, "aria-label": p.label + " 사용",
      onclick: function (event) { event.stopPropagation(); self.activate(p.id); } });
    var head = h("div", { class: "provider-head", onclick: function () {
      if (self.open.has(p.id)) self.open.delete(p.id); else self.open.add(p.id);
      self.render(false);
    } },
      radio, h("span", { class: "name" }, p.label), h("span", { class: "kind" }, KIND_LABEL[p.kind] || p.kind),
      h("span", { class: "state" }, h("i", { class: "dot " + (p.available ? "ok" : "bad") }), h("span", { title: p.detail }, p.available ? "사용 가능" : "설정 필요")));
    var inputs = {};
    var grid = h("div", { class: "form-grid" });
    p.options.forEach(function (option) {
      var id = "opt-" + p.id + "-" + option.key, input;
      if (option.kind === "secret") {
        input = h("input", { id: id, class: "text", type: "password", autocomplete: "off",
          placeholder: option.from_env ? option.env + " 환경 변수 사용 중" : option.has_value ? "저장됨 · 바꾸려면 새로 입력" : (option.placeholder || "") });
      } else {
        var listId = option.key === "model" && p.models.length ? id + "-list" : null;
        input = h("input", { id: id, class: "text", value: option.value || "", placeholder: option.default || option.placeholder || "",
          list: listId, spellcheck: "false" });
        if (listId) grid.append(h("datalist", { id: listId }, p.models.map(function (m) { return h("option", { value: m }); })));
      }
      inputs[option.key] = { input: input, option: option };
      grid.append(h("label", { for: id }, option.label), input);
      if (option.help) grid.append(h("div", { class: "help" }, option.help));
      if (option.key === "model" && p.models.length) grid.append(h("div", { class: "help" }, "서버의 모델: " + p.models.slice(0, 8).join(", ")));
    });
    var result = this.results[p.id];
    var body = h("div", { class: "provider-body" },
      h("p", { class: "desc" }, p.description, p.docs_url ? [" ", h("a", { href: p.docs_url, target: "_blank", rel: "noreferrer" }, "안내 문서")] : null),
      h("p", { class: "desc", style: "font-size:12px" }, "상태: " + p.detail),
      p.options.length ? grid : null,
      h("div", { class: "actions-row" },
        p.options.length ? h("button", { class: "btn", onclick: function () { self.save(p, inputs); } }, "저장") : null,
        h("button", { class: "btn", onclick: function (event) { self.test(p, event.currentTarget); } }, "연결 시험"),
        p.id !== activeId ? h("button", { class: "btn primary", onclick: function () { self.activate(p.id); } }, "이 AI 사용") : null,
        p.options.some(function (o) { return o.kind === "secret" && o.has_value && !o.from_env; }) ?
          h("button", { class: "btn danger", onclick: function () { self.clearSecrets(p); } }, "저장된 키 삭제") : null,
        result ? h("span", { class: "result " + (result.ok ? "ok" : "bad") }, result.text) : null));
    return h("div", { class: "provider" + (isOpen ? " open" : "") }, head, body);
  }

  async activate(id) {
    try {
      await this.app.api.put("/api/settings", { provider: id });
      this.open.add(id);
      await this.app.settings.load();
      toast("사용할 AI를 바꿨어요");
      this.render(false);
    } catch (error) { toast(error.message, true); }
  }

  async save(p, inputs) {
    var values = {};
    Object.keys(inputs).forEach(function (key) {
      var entry = inputs[key], value = entry.input.value.trim();
      if (entry.option.kind === "secret") { if (value) values[key] = value; }
      else values[key] = value;
    });
    try {
      await this.app.api.put("/api/providers/" + p.id, { values: values });
      await this.app.settings.load();
      toast("저장했어요");
      this.render(false);
    } catch (error) { toast(error.message, true); }
  }

  async clearSecrets(p) {
    var values = {};
    p.options.forEach(function (o) { if (o.kind === "secret") values[o.key] = null; });
    try {
      await this.app.api.put("/api/providers/" + p.id, { values: values });
      await this.app.settings.load();
      this.render(false);
    } catch (error) { toast(error.message, true); }
  }

  async test(p, button) {
    button.disabled = true;
    button.textContent = "시험 중…";
    try {
      var result = await this.app.api.post("/api/providers/" + p.id + "/test");
      this.results[p.id] = { ok: result.ok, text: result.ok ? "응답 받음 (" + result.seconds + "초" + (result.model ? ", " + result.model : "") + ")" : result.message };
    } catch (error) {
      this.results[p.id] = { ok: false, text: error.message };
    }
    this.render(false);
  }

  mcpSection() {
    return h("div", { class: "group" }, h("div", { class: "field-row", style: "display:block" },
      h("p", { class: "desc", style: "margin:0 0 6px;color:var(--text-2)" },
        "Claude 데스크톱이나 Codex 앱이 Paperdesk에 저장된 논문 목록·본문·검색 결과를 읽을 수 있게 연결해요. ",
        "이 방식은 각 앱이 공식 지원하는 MCP를 쓰고, 그 앱의 로그인 정보에는 접근하지 않아요. 터미널에서 아래 명령을 실행해 나온 내용을 각 앱 설정에 붙여 넣으세요."),
      h("pre", { class: "code" }, "paperdesk mcp-config claude   # Claude 데스크톱\npaperdesk mcp-config codex    # Codex")));
  }
}

