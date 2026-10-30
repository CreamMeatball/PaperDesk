import { analyzeDocument } from "./layout.js";

var pdfjsPromise = null;
export function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import("/vendor/pdfjs/pdf.min.mjs").then(function (lib) {
      lib.GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/pdf.worker.min.mjs";
      return lib;
    });
  }
  return pdfjsPromise;
}

function cleanTitle(value, filename) {
  var title = String(value || "").replace(/\s+/g, " ").trim();
  var stem = String(filename || "").replace(/\.pdf$/i, "").replace(/_/g, " ").trim();
  if (title.length < 6 || title.length > 300 || title.toLowerCase() === stem.toLowerCase()) return "";
  if (/^(untitled|title|paper|document|main|manuscript|submission|article|template|(?:neurips|icml|iclr|cvpr)[ _-]*\d*)$/i.test(title) || /^microsoft word\b/i.test(title)) return "";
  if (/\.(pdf|docx?|tex)$/i.test(title) || /^(?:arxiv:)?\d{4}\.\d{4,5}(?:v\d+)?$/i.test(title)) return "";
  return title;
}

export async function extractPdfTitle(pdf, filename) {
  try {
    var metadata = await pdf.getMetadata();
    var embedded = cleanTitle(metadata.info && metadata.info.Title, filename);
    if (embedded) return embedded;
  } catch (error) { console.warn("PDF metadata lookup failed", error); }
  var page = await pdf.getPage(1), content = await page.getTextContent(), viewport = page.getViewport({ scale: 1 });
  var analysis = analyzeDocument([{ items: content.items, view: page.view, width: viewport.width, height: viewport.height }]);
  var title = analysis.blocks.find(function (block) { return block.kind === "title"; });
  return title ? cleanTitle(title.text, "") : "";
}

export async function titleFromFile(file) {
  if (file.size > 200 * 1024 * 1024) return "";
  var lib = await loadPdfjs(), pdf;
  try {
    pdf = await lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false }).promise;
    return await extractPdfTitle(pdf, file.name);
  } finally { if (pdf) await pdf.destroy(); }
}

// Text and text positions of every page: the text for search, summaries and MCP, the positions for the layout
// analysis. alive() lets a closed reader stop early (then null).
export async function readPages(pdf, alive) {
  var texts = [], layout = [];
  for (var n = 1; n <= pdf.numPages; n++) {
    var page = await pdf.getPage(n);
    var content = await page.getTextContent();
    layout.push({ width: page.view[2] - page.view[0], height: page.view[3] - page.view[1], view: page.view, items: content.items, styles: content.styles });
    texts.push(content.items.map(function (item) { return (item.str || "") + (item.hasEOL ? "\n" : " "); }).join("")
      .replace(/[ \t]+\n/g, "\n").replace(/ {2,}/g, " ").trim());
    if (alive && !alive()) return null;
  }
  return { texts: texts, layout: layout };
}
