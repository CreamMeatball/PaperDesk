import { ApiClient } from "./js/api.js";
import { LibraryStore, SettingsModel } from "./js/store.js";
import { Router } from "./js/router.js";
import { Sidebar } from "./js/sidebar.js";
import { LibraryView } from "./js/library.js";
import { ReaderView } from "./js/reader.js";
import { AssistantPanel } from "./js/assistant.js";
import { SettingsView } from "./js/settings.js";
import { ReadingListView } from "./js/reading.js";
import { askText, confirmDialog, h, icon, modKey, toast } from "./js/ui.js";
import { pdfFiles } from "./js/dnd.js";

var VIEWS = { library: LibraryView, reader: ReaderView, settings: SettingsView };

// Application controller: owns shared state and the actions views call. Views stay dumb.
class App {
  constructor() {
    this.api = new ApiClient();
    this.store = new LibraryStore(this.api);
    this.settings = new SettingsModel(this.api);
    this.router = new Router();
    this.shell = document.getElementById("app");
    this.mainEl = document.getElementById("main");
    this.sidebar = new Sidebar(document.getElementById("sidebar"), this);
    this.assistant = new AssistantPanel(document.getElementById("assistant"), this);
    this.view = null;
    this.lastLibrary = "/library";
    this.fileInput = h("input", { type: "file", accept: "application/pdf,.pdf", multiple: true, hidden: true });
    document.body.append(this.fileInput);
    if (localStorage.getItem("paperdesk-sidebar") === "hidden") this.shell.classList.add("sidebar-hidden");
    if (localStorage.getItem("paperdesk-assistant") === "collapsed") this.shell.classList.add("assistant-collapsed");

    var self = this;
    this.router.addEventListener("change", function () { self.render(); });
    this.store.addEventListener("change", function () {
      self.sidebar.render();
      if (self.view && self.view.onStoreChange) self.view.onStoreChange();
    });
    document.addEventListener("keydown", function (event) { self.onShortcut(event); });
    // Dropping a PDF anywhere outside a specific target imports it into the current folder.
    document.addEventListener("dragover", function (event) { event.preventDefault(); });
    document.addEventListener("drop", function (event) {
      event.preventDefault();
      var files = pdfFiles(event.dataTransfer && event.dataTransfer.files);
      if (files.length) self.importFiles(files, self.currentFolder());
    });
  }

  async start() {
    if (location.pathname === "/") this.router.go("/library", true);
    try {
      await Promise.all([this.store.load(), this.settings.load()]);
    } catch (error) {
      toast(error.message, true);
    }
    this.render();
    if (!this.settings.data || !this.settings.data.provider) {
      toast("설정에서 사용할 AI를 고르면 번역·설명을 쓸 수 있어요.");
    }
  }

  render() {
    var route = this.router.route;
    if (route.name === "library") this.lastLibrary = location.pathname + location.search;
    if (this.view && this.view.destroy) this.view.destroy();
    this.mainEl.replaceChildren();
    this.shell.classList.toggle("with-assistant", route.name === "reader");
    var View = route.name === "library" && route.scope === "reading" ? ReadingListView : VIEWS[route.name];
    this.view = new View(this.mainEl, this, route);
    this.sidebar.render();
  }

  currentFolder() {
    var route = this.router.route;
    if (route.name === "library" && ["all", "recent", "unfiled", "reading"].indexOf(route.scope) < 0) return route.scope;
    return null;
  }

  // ---- layout ----
  sidebarHidden() { return this.shell.classList.contains("sidebar-hidden"); }
  toggleSidebar() {
    this.shell.classList.toggle("sidebar-hidden");
    localStorage.setItem("paperdesk-sidebar", this.sidebarHidden() ? "hidden" : "shown");
    if (this.view && this.view.render && !(this.view instanceof ReaderView)) this.view.render(false);
    if (this.view instanceof ReaderView) setTimeout(function () { window.dispatchEvent(new Event("resize")); }, 240);
  }
  toggleAssistant() {
    this.shell.classList.toggle("assistant-collapsed");
    localStorage.setItem("paperdesk-assistant", this.shell.classList.contains("assistant-collapsed") ? "collapsed" : "open");
    setTimeout(function () { window.dispatchEvent(new Event("resize")); }, 240);
  }
  showAssistant() {
    if (this.shell.classList.contains("assistant-collapsed")) this.toggleAssistant();
  }
  themeChanged() { this.sidebar.render(); }
  backToLibrary() { this.router.go(this.lastLibrary || "/library"); }
  search(query) { this.router.go(query ? "/library?q=" + encodeURIComponent(query) : "/library"); }
  openDocument(id, page) { this.router.go("/reader?id=" + id + (page && page > 1 ? "&page=" + page : "")); }

  // ---- files ----
  pickFiles(folderId) {
    var self = this;
    this.fileInput.value = "";
    this.fileInput.onchange = function () { self.importFiles(pdfFiles(self.fileInput.files), folderId); };
    this.fileInput.click();
  }

  async importFiles(files, folderId) {
    if (!files.length) { toast("PDF 파일만 추가할 수 있어요.", true); return; }
    toast(files.length + "개 파일을 추가하는 중…");
    var result = await this.store.upload(files, folderId);
    var parts = [];
    if (result.added) parts.push(result.added + "편 추가");
    if (result.existing) parts.push(result.existing + "편은 이미 있음");
    if (parts.length) toast(parts.join(", "));
    result.failed.forEach(function (message) { toast(message, true); });
  }

  // ---- folders ----
  async newFolder(parentId) {
    var parent = parentId ? this.store.folder(parentId) : null;
    var name = await askText({ title: parent ? "'" + parent.name + "' 안에 새 폴더" : "새 폴더", placeholder: "예: Diffusion, 강화학습, 읽을 거리", confirm: "만들기" });
    if (!name) return;
    try {
      var folder = await this.store.createFolder(name, parentId);
      this.router.go("/library?folder=" + folder.id);
    } catch (error) { toast(error.message, true); }
  }

  async renameFolder(folder) {
    var name = await askText({ title: "폴더 이름 바꾸기", value: folder.name, confirm: "바꾸기" });
    if (!name || name === folder.name) return;
    try { await this.store.renameFolder(folder.id, name); } catch (error) { toast(error.message, true); }
  }

  async deleteFolder(folder) {
    var count = this.store.countIn(folder.id);
    var ok = await confirmDialog({
      title: "'" + folder.name + "' 폴더를 삭제할까요?",
      message: count ? "안에 있는 논문 " + count + "편과 하위 폴더는 지워지지 않고 한 단계 위로 옮겨져요." : "빈 폴더예요.",
      confirm: "삭제", danger: true
    });
    if (!ok) return;
    var parent = folder.parent_id;
    try {
      await this.store.deleteFolder(folder.id);
      if (this.router.route.scope === folder.id) this.router.go(parent ? "/library?folder=" + parent : "/library", true);
    } catch (error) { toast(error.message, true); }
  }

  async moveFolder(id, parentId) {
    if (id === parentId) return;
    try { await this.store.moveFolder(id, parentId); if (parentId) this.store.setExpanded(parentId, true); }
    catch (error) { toast(error.message, true); }
  }

  async moveDocuments(ids, folderId) {
    try {
      for (var i = 0; i < ids.length; i++) await this.api.patch("/api/documents/" + ids[i], { folder_id: folderId || null });
      await this.store.load();
      var folder = folderId ? this.store.folder(folderId) : null;
      toast(ids.length + "편을 '" + (folder ? folder.name : "분류 안 됨") + "'(으)로 옮겼어요");
    } catch (error) { toast(error.message, true); await this.store.load(); }
  }

  // Folder picker: target = {documents: [ids]} or {folder: folder}
  chooseFolderFor(target) {
    var self = this, store = this.store;
    var blocked = target.folder ? store.descendants(target.folder.id) : new Set();
    if (target.folder) blocked.add(target.folder.id);
    var list = h("div", { class: "menu", style: "position:static;box-shadow:none;border:0;background:transparent;max-height:50vh;overflow:auto;padding:0" });
    var backdrop = h("div", { class: "backdrop", onmousedown: function (event) { if (event.target === backdrop) backdrop.remove(); } },
      h("div", { class: "dialog" }, h("h3", null, target.folder ? "'" + target.folder.name + "' 옮기기" : "폴더로 옮기기"), list,
        h("div", { class: "buttons" }, h("button", { class: "btn", onclick: function () { backdrop.remove(); } }, "취소"))));
    function choose(folderId) {
      backdrop.remove();
      if (target.folder) self.moveFolder(target.folder.id, folderId);
      else self.moveDocuments(target.documents, folderId);
    }
    list.append(h("button", { onclick: function () { choose(null); } }, icon(target.folder ? "books" : "inbox"), target.folder ? "맨 위" : "분류 안 됨"));
    (function walk(parentId, depth) {
      store.children(parentId).forEach(function (folder) {
        if (blocked.has(folder.id)) return;
        list.append(h("button", { style: "padding-left:" + (9 + depth * 16) + "px", onclick: function () { choose(folder.id); } }, icon("folder"), folder.name));
        walk(folder.id, depth + 1);
      });
    })(null, 0);
    document.body.append(backdrop);
  }

  // ---- reading list ----
  async addToReadingList(citation, sourceDocId) {
    try {
      var result = await this.store.addReading(citation, sourceDocId);
      toast(result.created ? "'" + result.item.title + "'을(를) 읽어볼 논문에 추가했어요" : "이미 읽어볼 논문에 있어요");
      return result.item;
    } catch (error) {
      toast(error.message, true);
      return null;
    }
  }

  // ---- documents ----
  async renameDocument(doc) {
    var title = await askText({ title: "논문 이름 바꾸기", value: doc.title, confirm: "바꾸기" });
    if (!title || title === doc.title) return;
    try {
      await this.store.renameDocument(doc.id, title);
      if (this.view instanceof ReaderView) this.view.titleEl.textContent = title;
    } catch (error) { toast(error.message, true); }
  }

  async deleteDocuments(ids) {
    var single = ids.length === 1 ? this.store.document(ids[0]) : null;
    var ok = await confirmDialog({
      title: single ? "'" + single.title + "'을(를) 삭제할까요?" : ids.length + "편을 삭제할까요?",
      message: "PDF와 AI 대화 기록이 이 컴퓨터에서 지워져요.", confirm: "삭제", danger: true
    });
    if (!ok) return;
    try {
      for (var i = 0; i < ids.length; i++) {
        await this.api.del("/api/documents/" + ids[i]);
        localStorage.removeItem("paperdesk-thread:" + ids[i]);
      }
      await this.store.load();
    } catch (error) { toast(error.message, true); }
  }

  // ---- keyboard ----
  onShortcut(event) {
    if (!modKey(event)) return;
    var key = event.key.toLowerCase();
    if (key === "k") { event.preventDefault(); if (this.sidebarHidden()) this.toggleSidebar(); this.sidebar.searchInput.focus(); }
    else if (key === "o") { event.preventDefault(); this.pickFiles(this.currentFolder()); }
    else if (key === ",") { event.preventDefault(); this.router.go("/settings"); }
    else if (key === "\\") { event.preventDefault(); this.toggleSidebar(); }
    else if (key === "j" && this.router.route.name === "reader") { event.preventDefault(); this.toggleAssistant(); }
  }
}

window.paperdesk = new App();
window.paperdesk.start();

