// Maps the rendered pdf.js text layer of one page to strings and back to on-screen rectangles.
// compact = text without whitespace (stable between analysis text and the DOM); spaced = text with single spaces (for regexes).

export class TextMap {
  constructor(pageEl) {
    this.el = pageEl;
    this.page = Number(pageEl.dataset.page);
    this.nodes = [];
    this.nodeStart = [];   // compact index where each text node begins
    this.charNode = [];    // compact index -> node index
    this.charOffset = [];  // compact index -> offset inside node
    this.segments = [];    // spaced string segments {node, start}
    var layer = pageEl.querySelector(".textLayer"), compact = "", spaced = "", parent = null, node;
    var walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT);
    while ((node = walker.nextNode())) {
      var index = this.nodes.length;
      this.nodes.push(node);
      this.nodeStart.push(compact.length);
      for (var i = 0; i < node.data.length; i++) {
        var ch = node.data[i];
        if (/[\s\u00ad]/.test(ch)) continue;
        compact += ch;
        this.charNode.push(index);
        this.charOffset.push(i);
      }
      if (spaced && node.parentNode !== parent) spaced += " ";
      this.segments.push({ node: node, start: spaced.length });
      spaced += node.data;
      parent = node.parentNode;
    }
    this.compact = compact;
    this.lower = compact.toLowerCase();
    this.spaced = spaced;
    this.blockCache = new Map();
  }

  // ---- compact positions ----
  range(start, end) {
    if (start < 0 || end <= start || end > this.compact.length) return null;
    var range = document.createRange();
    range.setStart(this.nodes[this.charNode[start]], this.charOffset[start]);
    range.setEnd(this.nodes[this.charNode[end - 1]], this.charOffset[end - 1] + 1);
    return range;
  }

  rects(start, end) { var r = this.range(start, end); return r ? this.normalize(r) : []; }

  normalize(range) {
    var base = this.el.getBoundingClientRect(), out = [];
    Array.prototype.forEach.call(range.getClientRects(), function (r) {
      if (r.width < 0.5 || r.height < 0.5) return;
      var rect = [(r.left - base.left) / base.width, (r.top - base.top) / base.height, (r.right - base.left) / base.width, (r.bottom - base.top) / base.height];
      var last = out[out.length - 1];
      if (last && Math.abs(last[1] - rect[1]) < 0.006 && rect[0] - last[2] < 0.02 && rect[0] >= last[0] - 0.001) {
        last[2] = Math.max(last[2], rect[2]); last[3] = Math.max(last[3], rect[3]); last[1] = Math.min(last[1], rect[1]);
      } else out.push(rect);
    });
    return out;
  }

  // Locate an analysis block (only its lines on this page); returns [{blockStart, pageStart, length}] or null.
  // Lines usually match exactly; when the text layer has extra characters (sub/superscripts kept out of the
  // analysed line) the line is matched as a subsequence and split into contiguous runs.
  locateBlock(block) {
    if (this.blockCache.has(block.key)) return this.blockCache.get(block.key);
    var segments = [], blockOffset = 0, cursor = 0, self = this;
    block.lines.forEach(function (line) {
      var needle = line.text.replace(/[\s\u00ad]+/g, "");
      if (!needle) return;
      if (line.page === self.page) {
        var at = self.compact.indexOf(needle, cursor);
        if (at < 0) at = self.compact.indexOf(needle);
        if (at >= 0) {
          segments.push({ blockStart: blockOffset, pageStart: at, length: needle.length });
          cursor = at + needle.length;
        } else {
          var runs = self.fuzzy(needle, cursor);
          runs.forEach(function (r) { segments.push({ blockStart: blockOffset + r.needle, pageStart: r.page, length: r.length }); });
          if (runs.length) cursor = runs[runs.length - 1].page + runs[runs.length - 1].length;
        }
      }
      blockOffset += needle.length;
    });
    var result = segments.length ? segments : null;
    this.blockCache.set(block.key, result);
    return result;
  }

  // Subsequence match anchored on the first few characters; tolerates up to 6 extra page characters per gap
  // and skips needle characters that the text layer lacks. Returns contiguous runs.
  fuzzy(needle, from) {
    var hay = this.compact, anchorLen = Math.min(8, needle.length), start = -1;
    for (var shift = 0; shift < Math.min(needle.length - anchorLen + 1, 20) && start < 0; shift++) {
      var anchor = needle.substr(shift, anchorLen), at = hay.indexOf(anchor, from);
      if (at < 0) at = hay.indexOf(anchor);
      if (at >= 0) start = { needle: shift, page: at };
    }
    if (!start || start === -1) return [];
    var runs = [], i = start.needle, j = start.page, run = null, matched = 0;
    while (i < needle.length && j < hay.length) {
      if (needle[i] === hay[j]) {
        if (run && run.needle + run.length === i && run.page + run.length === j) run.length++;
        else { run = { needle: i, page: j, length: 1 }; runs.push(run); }
        i++; j++; matched++;
        continue;
      }
      var skip = hay.slice(j, j + 7).indexOf(needle[i]);
      if (skip > 0) { j += skip; continue; }
      i++; // character missing from the text layer
    }
    return matched >= needle.length * 0.7 ? runs : [];
  }

  // Block-compact [start, end) -> rects on the page.
  blockRects(block, start, end) {
    var segments = this.locateBlock(block), out = [], self = this;
    if (!segments) return out;
    segments.forEach(function (s) {
      var a = Math.max(start, s.blockStart), b = Math.min(end, s.blockStart + s.length);
      if (b > a) out.push.apply(out, self.rects(s.pageStart + a - s.blockStart, s.pageStart + b - s.blockStart));
    });
    return out;
  }

  // Page-compact index -> block-compact offset for this block, or -1.
  blockOffsetOf(block, pageIndex) {
    var segments = this.locateBlock(block);
    if (!segments) return -1;
    for (var i = 0; i < segments.length; i++) {
      var s = segments[i];
      if (pageIndex >= s.pageStart && pageIndex < s.pageStart + s.length) return s.blockStart + pageIndex - s.pageStart;
    }
    return -1;
  }

  // Compact index of the character under the pointer, or -1 when the pointer is not on text.
  hitTest(x, y) {
    var node, offset;
    if (document.caretRangeFromPoint) {
      var r = document.caretRangeFromPoint(x, y);
      if (!r) return -1;
      node = r.startContainer; offset = r.startOffset;
    } else if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(x, y);
      if (!p) return -1;
      node = p.offsetNode; offset = p.offset;
    } else return -1;
    var index = this.nodes.indexOf(node);
    if (index < 0) return -1;
    var compactIndex = this.nodeStart[index];
    for (var i = 0; i < Math.min(offset, node.data.length); i++) if (!/[\s\u00ad]/.test(node.data[i])) compactIndex++;
    if (compactIndex >= this.compact.length) compactIndex = this.compact.length - 1;
    var range = this.range(compactIndex, compactIndex + 1);
    if (!range) return -1;
    var box = range.getBoundingClientRect();
    if (x < box.left - 4 || x > box.right + 4 || y < box.top - 3 || y > box.bottom + 3) return -1;
    return compactIndex;
  }

  // ---- spaced positions (regex matches) ----
  spacedRange(start, end) {
    function locate(segments, offset, isEnd) {
      for (var i = segments.length - 1; i >= 0; i--) {
        var s = segments[i];
        if (isEnd ? s.start < offset : s.start <= offset) return { node: s.node, offset: Math.min(offset - s.start, s.node.data.length) };
      }
      return null;
    }
    var a = locate(this.segments, start, false), b = locate(this.segments, end, true);
    if (!a || !b) return null;
    var range = document.createRange();
    try { range.setStart(a.node, a.offset); range.setEnd(b.node, b.offset); } catch (error) { return null; }
    return range;
  }

  spacedRects(start, end) { var r = this.spacedRange(start, end); return r ? this.normalize(r) : []; }
}

export function drawRects(layer, rects, className, extra) {
  var nodes = rects.map(function (r) {
    var div = document.createElement("div");
    div.className = className;
    div.style.cssText = "left:" + (r[0] * 100) + "%;top:" + (r[1] * 100) + "%;width:" + ((r[2] - r[0]) * 100) + "%;height:" + ((r[3] - r[1]) * 100) + "%";
    if (extra) extra(div);
    layer.append(div);
    return div;
  });
  return nodes;
}

export function rectContains(rect, x, y, padX, padY) {
  return x >= rect[0] - (padX || 0) && x <= rect[2] + (padX || 0) && y >= rect[1] - (padY || 0) && y <= rect[3] + (padY || 0);
}

