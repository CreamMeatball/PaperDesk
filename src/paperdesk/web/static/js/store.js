import { t } from "./i18n.js";
// Client-side model of the library: folders + documents, with tree helpers. Views listen for "change".

function normalize(text) { return String(text || "").replace(/\u00ad/g, "").replace(/\s+/g, " ").trim(); }

export class LibraryStore extends EventTarget {
  constructor(api) {
    super();
    this.api = api;
    this.folders = [];
    this.documents = [];
    this.readingList = [];
    var saved = [];
    try { saved = JSON.parse(localStorage.getItem("paperdesk-expanded") || "[]"); } catch (error) { saved = []; }
    this.expanded = new Set(saved);
  }

  async load() {
    var data = await this.api.get("/api/library");
    this.folders = data.folders;
    this.documents = data.documents;
    this.readingList = data.reading_list || [];
    this.changed();
  }

  changed() { this.dispatchEvent(new Event("change")); }

  folder(id) { return this.folders.find(function (f) { return f.id === id; }) || null; }
  document(id) { return this.documents.find(function (d) { return d.id === id; }) || null; }

  children(parentId) {
    return this.folders
      .filter(function (f) { return (f.parent_id || null) === (parentId || null); })
      .sort(function (a, b) { return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }); });
  }

  descendants(id) {
    var found = new Set(), stack = [id], self = this;
    while (stack.length) {
      self.children(stack.pop()).forEach(function (child) {
        if (!found.has(child.id)) { found.add(child.id); stack.push(child.id); }
      });
    }
    return found;
  }

  path(id) {
    var chain = [], current = this.folder(id);
    while (current) { chain.unshift(current); current = this.folder(current.parent_id); }
    return chain;
  }

  countIn(folderId) {
    var wanted = this.descendants(folderId);
    wanted.add(folderId);
    return this.documents.filter(function (d) { return wanted.has(d.folder_id); }).length;
  }

  documentsIn(scope) {
    if (scope === "unfiled") return this.documents.filter(function (d) { return !d.folder_id; });
    if (scope === "recent") {
      return this.documents.filter(function (d) { return d.last_opened_at; })
        .sort(function (a, b) { return b.last_opened_at.localeCompare(a.last_opened_at); }).slice(0, 30);
    }
    if (scope && scope !== "all") return this.documents.filter(function (d) { return d.folder_id === scope; });
    return this.documents.slice();
  }

  isExpanded(id) { return this.expanded.has(id); }
  setExpanded(id, open) {
    if (open) this.expanded.add(id); else this.expanded.delete(id);
    try { localStorage.setItem("paperdesk-expanded", JSON.stringify(Array.from(this.expanded))); } catch (error) {}
    this.changed();
  }

  async createFolder(name, parentId) {
    var data = await this.api.post("/api/folders", { name: name, parent_id: parentId || null });
    if (parentId) this.expanded.add(parentId);
    await this.load();
    return data.folder;
  }
  async renameFolder(id, name) { await this.api.patch("/api/folders/" + id, { name: name }); await this.load(); }
  async moveFolder(id, parentId) { await this.api.patch("/api/folders/" + id, { parent_id: parentId || null }); await this.load(); }
  async deleteFolder(id) { await this.api.del("/api/folders/" + id); await this.load(); }
  async renameDocument(id, title) { await this.api.patch("/api/documents/" + id, { title: title }); await this.load(); }
  async moveDocument(id, folderId) { await this.api.patch("/api/documents/" + id, { folder_id: folderId || null }); await this.load(); }
  async deleteDocument(id) { await this.api.del("/api/documents/" + id); await this.load(); }

  // ---- reading list ----
  findReading(citation) {
    var wanted = normalize(citation);
    return this.readingList.find(function (item) { return normalize(item.citation) === wanted; }) || null;
  }
  async addReading(citation, sourceDocId) {
    var result = await this.api.post("/api/reading-list", { citation: citation, source_doc_id: sourceDocId || null });
    await this.load();
    return result;
  }
  async renameReading(id, title) { await this.api.patch("/api/reading-list/" + id, { title: title }); await this.load(); }
  async removeReading(id) { await this.api.del("/api/reading-list/" + id); await this.load(); }
  async fetchArxiv(id) { var result = await this.api.post("/api/reading-list/" + id + "/arxiv", {}); await this.load(); return result; }
  async attachReadingPdf(id, file) {
    var result = await this.api.request("POST", "/api/reading-list/" + id + "/pdf", file,
      { "Content-Type": "application/pdf", "X-Filename": encodeURIComponent(file.name) });
    await this.load();
    return result;
  }

  async upload(files, folderId) {
    var added = 0, existing = 0, failed = [];
    for (var i = 0; i < files.length; i++) {
      try {
        var result = await this.api.upload(files[i], folderId);
        if (result.created) added++; else existing++;
      } catch (error) {
        failed.push(files[i].name + ": " + error.message);
      }
    }
    await this.load();
    return { added: added, existing: existing, failed: failed };
  }
}

export class SettingsModel extends EventTarget {
  constructor(api) {
    super();
    this.api = api;
    this.data = null;
  }
  async load() {
    this.data = await this.api.get("/api/settings");
    this.dispatchEvent(new Event("change"));
    return this.data;
  }
  active() {
    if (!this.data || !this.data.provider) return null;
    var id = this.data.provider;
    return this.data.providers.find(function (p) { return p.id === id; }) || null;
  }
}

