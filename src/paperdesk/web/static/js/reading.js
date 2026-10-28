import { askText, h, icon, iconButton, menuAt, relativeTime, showMenu, toast } from "./ui.js";
import { t } from "./i18n.js";

// '읽어볼 논문' list: papers saved from citations, waiting for their PDF.
export class ReadingListView {
  constructor(root, app, route) {
    this.root = root;
    this.app = app;
    this.render();
  }

  onStoreChange() { this.render(); }

  render() {
    var app = this.app, self = this, items = app.store.readingList;
    var waiting = items.filter(function (i) { return !i.in_library; }).length;
    var toolbar = h("div", { class: "toolbar" },
      app.sidebarHidden() ? iconButton("sidebar", t("사이드바 보이기"), function () { app.toggleSidebar(); }) : null,
      h("h1", null, t("읽어볼 논문")),
      h("span", { class: "sub" }, items.length ? t("읽기 전 {a}편 · 서재에 있음 {b}편", { a: waiting, b: items.length - waiting }) : ""),
      h("span", { class: "spacer" }),
      h("button", { class: "btn", onclick: function () { self.addManually(); } }, icon("plus"), t("직접 추가")));
    var body = h("div", { class: "library" });
    if (!items.length) {
      body.append(h("div", { class: "empty-state" }, h("div", null,
        h("div", { class: "art" }, icon("bookmark")),
        h("h2", null, t("읽어볼 논문이 없어요")),
        h("p", null, t("논문을 읽다가 [12]나 Smith et al. (2020) 같은 인용에 마우스를 올리고 ‘읽어볼 논문에 추가’를 누르세요.")),
        h("button", { class: "btn", onclick: function () { self.addManually(); } }, icon("plus"), t("직접 추가")))));
    } else {
      var tbody = h("tbody");
      items.forEach(function (item) { tbody.append(self.row(item)); });
      body.append(h("table", { class: "table" },
        h("thead", null, h("tr", null, h("th", null, t("논문")), h("th", null, t("인용한 논문")), h("th", null, t("상태")), h("th", null, t("추가함")), h("th"))),
        tbody));
    }
    this.root.replaceChildren(toolbar, body);
  }

  row(item) {
    var app = this.app, self = this;
    var source = item.source_doc_id ? app.store.document(item.source_doc_id) : null;
    var meta = [item.authors && item.authors.length > 90 ? item.authors.slice(0, 90) + "…" : item.authors, item.year].filter(Boolean).join(" · ");
    var status = item.in_library
      ? h("button", { class: "chip ok", onclick: function () { app.openDocument(item.document_id); } }, t("서재에 있음 · 열기"))
      : h("span", { class: "chip" }, t("읽기 전"));
    var get = null;
    if (!item.in_library) {
      get = item.arxiv_id
        ? h("button", { class: "btn small primary", onclick: function (event) { self.fetchArxiv(item, event.currentTarget); } }, icon("upload", 13), t("arXiv PDF 받기"))
        : h("button", { class: "btn small", onclick: function () { self.attachPdf(item); } }, icon("upload", 13), t("PDF 추가"));
    }
    return h("tr", { class: "row tall", ondblclick: function () { if (item.in_library) app.openDocument(item.document_id); },
      oncontextmenu: function (event) { event.preventDefault(); showMenu(event.clientX, event.clientY, self.menu(item)); } },
      h("td", { class: "title", title: item.citation },
        h("div", { class: "doc-title" }, icon(item.in_library ? "file" : "bookmark"), h("span", null, item.title)),
        meta ? h("div", { class: "meta-line" }, meta) : null),
      h("td", null, source ? h("button", { class: "link-btn", onclick: function () { app.openDocument(source.id); } }, source.title) : "—"),
      h("td", null, status),
      h("td", null, relativeTime(item.created_at)),
      h("td", { class: "actions wide" }, get, iconButton("more", t("메뉴"), function (event) { menuAt(event.currentTarget, self.menu(item)); })));
  }

  menu(item) {
    var app = this.app, self = this;
    var links = [];
    if (item.arxiv_id) links.push({ label: t("arXiv에서 보기"), icon: "external", onClick: function () { window.open("https://arxiv.org/abs/" + item.arxiv_id, "_blank"); } });
    if (item.doi) links.push({ label: t("DOI로 보기"), icon: "external", onClick: function () { window.open("https://doi.org/" + item.doi, "_blank"); } });
    links.push({ label: t("Google Scholar에서 찾기"), icon: "search", onClick: function () {
      window.open("https://scholar.google.com/scholar?q=" + encodeURIComponent(item.title), "_blank");
    } });
    return [
      item.in_library ? { label: t("서재에서 열기"), icon: "file", onClick: function () { app.openDocument(item.document_id); } } : null,
      item.in_library ? null : { label: t("PDF 파일 추가…"), icon: "upload", onClick: function () { self.attachPdf(item); } },
      { label: t("제목 고치기"), icon: "pencil", onClick: function () { self.rename(item); } },
      { label: t("인용문 복사"), icon: "copy", onClick: function () { navigator.clipboard.writeText(item.citation); toast(t("복사했어요")); } },
      "-"
    ].concat(links, ["-", { label: t("목록에서 빼기"), icon: "trash", danger: true, onClick: function () { app.store.removeReading(item.id); } }]).filter(Boolean);
  }

  async addManually() {
    var text = await askText({ title: t("읽어볼 논문 추가"), message: t("참고문헌 한 줄이나 논문 제목·arXiv 주소를 붙여 넣으세요."),
      placeholder: t("예: Ho et al. Denoising diffusion probabilistic models. arXiv:2006.11239"), confirm: t("추가") });
    if (text) await this.app.addToReadingList(text, null);
  }

  async rename(item) {
    var title = await askText({ title: t("제목 고치기"), value: item.title, confirm: t("저장") });
    if (title && title !== item.title) {
      try { await this.app.store.renameReading(item.id, title); } catch (error) { toast(error.message, true); }
    }
  }

  async fetchArxiv(item, button) {
    button.disabled = true;
    button.textContent = t("받는 중…");
    try {
      var result = await this.app.store.fetchArxiv(item.id);
      var folder = result.document.folder_id ? this.app.store.folder(result.document.folder_id) : null;
      toast(folder ? t("'{title}'을(를) '{folder}' 폴더에 넣었어요", { title: result.document.title, folder: folder.name }) : t("'{title}'을(를) 서재에 넣었어요", { title: result.document.title }));
    } catch (error) {
      toast(error.message, true);
      this.render();
    }
  }

  attachPdf(item) {
    var app = this.app, input = h("input", { type: "file", accept: "application/pdf,.pdf", hidden: true });
    input.onchange = async function () {
      var file = input.files[0];
      input.remove();
      if (!file) return;
      try {
        var result = await app.store.attachReadingPdf(item.id, file);
        toast(t("'{title}'을(를) 서재에 넣었어요", { title: result.document.title }));
      } catch (error) { toast(error.message, true); }
    };
    document.body.append(input);
    input.click();
  }
}

