import { t } from "./i18n.js";
// Markdown + KaTeX for AI answers. marked, DOMPurify and katex are loaded as classic scripts in index.html.

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
}

var MATH = /(\x60{3}[\s\S]*?\x60{3}|\x60[^\x60\n]*\x60)|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$\$([\s\S]*?)\$\$|\$([^\n$]+?)\$/g;

// Inline math only (for translation cards): returns a fragment; plain-text parts go through onText.
export function renderInlineMath(text, onText) {
  var fragment = document.createDocumentFragment(), last = 0, match;
  var re = /\\\(([\s\S]+?)\\\)|\$([^\n$]+?)\$/g;
  while ((match = re.exec(text))) {
    if (/^\d[\d,.]*\s+[A-Za-z가-힣]/.test(match[2] || "")) continue;
    fragment.append(onText(text.slice(last, match.index)));
    var span = document.createElement("span");
    span.className = "math";
    try { span.innerHTML = window.katex.renderToString(match[1] || match[2], { throwOnError: true, trust: false, strict: "ignore", maxExpand: 500 }); }
    catch (error) { span.textContent = match[0]; span.classList.add("math-fallback"); }
    fragment.append(span);
    last = re.lastIndex;
  }
  fragment.append(onText(text.slice(last)));
  return fragment;
}

export function renderMarkdown(node, source) {
  // Protect LaTeX before Markdown consumes its backslashes and underscores.
  var formulas = [], prefix = "PDMATH" + Math.random().toString(36).slice(2) + "X";
  var text = String(source || "").replace(MATH, function (raw, code, block, inline, dollars, single) {
    if (code) return raw;
    if (single && /^\d[\d,.]*\s+[A-Za-z가-힣]/.test(single)) return raw; // "$0.10 input, $0.50 output"
    formulas.push({ raw: raw, tex: block != null ? block : inline != null ? inline : dollars != null ? dollars : single,
      display: block != null || dollars != null });
    return prefix + (formulas.length - 1) + "END";
  });
  // CommonMark ignores "**term (EN)**를" (closing ** after punctuation must not touch a letter); Korean particles always do.
  text = text.split(/(\x60{3}[\s\S]*?\x60{3}|\x60[^\x60\n]*\x60)/).map(function (part, index) {
    return index % 2 ? part : part.replace(/\*\*(?=\S)([^\n]*?\S)\*\*/g, "<strong>$1</strong>");
  }).join("");
  var html = window.marked ? window.marked.parse(text, { gfm: true, breaks: true }) : escapeHtml(text).replace(/\n/g, "<br>");
  var clean = window.DOMPurify
    ? window.DOMPurify.sanitize(html, { RETURN_DOM_FRAGMENT: true, FORBID_TAGS: ["style", "img", "form", "input", "iframe"] })
    : document.createTextNode(source || "");
  node.replaceChildren(clean);
  if (formulas.length) {
    var walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT), targets = [], current;
    while ((current = walker.nextNode())) {
      if (current.data.indexOf(prefix) >= 0 && !current.parentElement.closest("pre,code")) targets.push(current);
    }
    targets.forEach(function (target) {
      var re = new RegExp(prefix + "(\\d+)END", "g"), match, offset = 0, fragment = document.createDocumentFragment();
      while ((match = re.exec(target.data))) {
        fragment.append(document.createTextNode(target.data.slice(offset, match.index)));
        var formula = formulas[Number(match[1])], span = document.createElement("span");
        span.className = formula.display ? "math display" : "math";
        try {
          span.innerHTML = window.katex.renderToString(formula.tex, { displayMode: formula.display, throwOnError: true, trust: false, strict: "ignore", maxExpand: 1000 });
        } catch (error) {
          span.textContent = formula.raw;
          span.classList.add("math-fallback");
        }
        fragment.append(span);
        offset = re.lastIndex;
      }
      fragment.append(document.createTextNode(target.data.slice(offset)));
      target.replaceWith(fragment);
    });
  }
  node.querySelectorAll("a").forEach(function (a) { a.target = "_blank"; a.rel = "noopener noreferrer"; });
  return node;
}

