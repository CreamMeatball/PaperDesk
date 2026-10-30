// After an import with automatic translation on, translate the paper in the background so it is ready when opened.
// These are the reader's steps without a reader: text from pdf.js, the Docling analysis, then one translation job.
import { loadPdfjs, readPages } from "./pdf.js";
import { analyzeDocling } from "./layout.js";

var POLL = 2000, ANALYSIS_LIMIT = 15 * 60 * 1000;

function wait(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }

export class BackgroundTranslation {
  constructor(app) {
    this.app = app;
    this.queue = Promise.resolve();  // one paper at a time
  }

  add(ids) {
    var self = this;
    ids.forEach(function (id) {
      self.queue = self.queue.then(function () { return self.translate(id); })
        .catch(function (error) { console.warn("background translation", id, error); });
    });
  }

  async translate(id) {
    var app = this.app, api = app.api, provider = app.settings.active();
    if (!app.settings.data || !app.settings.data.auto_translate || !provider || !provider.available) return;
    var lib = await loadPdfjs();
    var pdf = await lib.getDocument({ url: "/api/documents/" + id + "/file", isEvalSupported: false }).promise;
    try {
      if (pdf.numPages > 500) return;  // the reader refuses these as well
      var pages = await readPages(pdf);
      var doc = (await api.get("/api/documents/" + id)).document;
      if (doc.text_pages !== pages.texts.length) await api.put("/api/documents/" + id + "/text", { pages: pages.texts });
      var layout = await this.analysis(id);
      if (!layout) return;
      var blocks = analyzeDocling(pages.layout, layout).blocks.filter(function (b) { return b.translatable; });
      var saved = await api.get("/api/documents/" + id + "/translations");
      var jobs = (await api.get("/api/documents/" + id + "/translation-jobs")).jobs;
      // Opened meanwhile, the reader may have started one already (and the server never queues a paragraph twice).
      if (jobs.some(function (job) { return job.language === saved.language && job.state !== "completed"; })) return;
      var fresh = blocks.filter(function (b) { return !saved.blocks[b.key]; });
      if (fresh.length) await api.post("/api/documents/" + id + "/translation-jobs", {
        blocks: fresh.map(function (b) { return { key: b.key, sentences: b.sentences }; }), title: doc.title, terms: "" });
    } finally {
      pdf.destroy();
    }
  }

  async analysis(id) {
    var api = this.app.api, data = await api.post("/api/documents/" + id + "/analysis", { retry: false });
    for (var end = Date.now() + ANALYSIS_LIMIT; data.state !== "completed" && data.state !== "failed" && Date.now() < end;) {
      await wait(POLL);
      data = await api.get("/api/documents/" + id + "/analysis");
    }
    return data.state === "completed" ? data.layout : null;
  }
}
