// Small DOM helpers shared by every view. No framework on purpose: fewer moving parts to package.

var ICONS = {
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l1.5 2h5.5A1.5 1.5 0 0 1 17 8.5v6A1.5 1.5 0 0 1 15.5 16h-11A1.5 1.5 0 0 1 3 14.5z"/>',
  folderPlus: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l1.5 2h5.5A1.5 1.5 0 0 1 17 8.5v6A1.5 1.5 0 0 1 15.5 16h-11A1.5 1.5 0 0 1 3 14.5z"/><path d="M10 9.5v4M8 11.5h4"/>',
  inbox: '<path d="M3 11h4l1 2h4l1-2h4"/><path d="M5 5h10l2 6v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-4z"/>',
  books: '<path d="M4 4h3v12H4zM8.5 4h3v12h-3z"/><path d="m13 4.6 2.8-.7 2.4 11.6-2.8.6z"/>',
  clock: '<circle cx="10" cy="10" r="7"/><path d="M10 6v4l2.5 1.5"/>',
  file: '<path d="M6 3h5.5L15 6.5V16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M11 3v4h4"/>',
  search: '<circle cx="9" cy="9" r="5"/><path d="m13 13 4 4"/>',
  settings: '<circle cx="10" cy="10" r="2.5"/><path d="M10 2.5v2M10 15.5v2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M2.5 10h2M15.5 10h2M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"/>',
  plus: '<path d="M10 4v12M4 10h12"/>',
  upload: '<path d="M10 13V4M6.5 7.5 10 4l3.5 3.5"/><path d="M4 13v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/>',
  chevron: '<path d="m8 5 5 5-5 5"/>',
  back: '<path d="m12 5-5 5 5 5"/>',
  more: '<circle cx="5" cy="10" r=".9"/><circle cx="10" cy="10" r=".9"/><circle cx="15" cy="10" r=".9"/>',
  sidebar: '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M8 4v12"/>',
  panel: '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M12 4v12"/>',
  translate: '<path d="M3 5h8M7 3v2M5 5c0 3 2 5 5 6M9 5c0 3-2 5-5 6"/><path d="m11 17 3-7 3 7M12 15h4"/>',
  sparkle: '<path d="M10 3c.6 3.4 1.9 4.7 5.3 5.3-3.4.6-4.7 1.9-5.3 5.3-.6-3.4-1.9-4.7-5.3-5.3C8.1 7.7 9.4 6.4 10 3z"/><path d="M15.5 13c.2 1.2.7 1.7 1.9 1.9-1.2.2-1.7.7-1.9 1.9-.2-1.2-.7-1.7-1.9-1.9 1.2-.2 1.7-.7 1.9-1.9z"/>',
  question: '<circle cx="10" cy="10" r="7"/><path d="M8 8a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.2v.5M10 14h.01"/>',
  send: '<path d="M10 16V4M5.5 8.5 10 4l4.5 4.5"/>',
  trash: '<path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10"/>',
  pencil: '<path d="m4 16 1-4 8-8 3 3-8 8z"/>',
  move: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l1.5 2h5.5A1.5 1.5 0 0 1 17 8.5v6A1.5 1.5 0 0 1 15.5 16h-11A1.5 1.5 0 0 1 3 14.5z"/><path d="m10 9.5 2 2-2 2M7.5 11.5H12"/>',
  sun: '<circle cx="10" cy="10" r="3"/><path d="M10 2.5v1.5M10 16v1.5M2.5 10H4M16 10h1.5M4.7 4.7l1 1M14.3 14.3l1 1M4.7 15.3l1-1M14.3 5.7l1-1"/>',
  moon: '<path d="M15.5 12.5A6 6 0 0 1 7.5 4.5a6 6 0 1 0 8 8z"/>',
  monitor: '<rect x="3" y="4" width="14" height="10" rx="1.5"/><path d="M7 17h6M10 14v3"/>',
  copy: '<rect x="7" y="7" width="9" height="9" rx="1.5"/><path d="M4 13V5a1 1 0 0 1 1-1h8"/>',
  close: '<path d="m5 5 10 10M15 5 5 15"/>',
  chevronDown: '<path d="m5 8 5 5 5-5"/>',
  chevronUp: '<path d="m5 12 5-5 5 5"/>',
  list: '<path d="M7 5h10M7 10h10M7 15h10"/><circle cx="3.6" cy="5" r=".8"/><circle cx="3.6" cy="10" r=".8"/><circle cx="3.6" cy="15" r=".8"/>',
  crop: '<path d="M5 2.5V15h12.5"/><path d="M2.5 5H15v12.5"/>',
  highlighter: '<path d="m11.5 4.5 4 4-6.5 6.5H5v-4z"/><path d="M3 17.5h7"/>',
  note: '<path d="M4 3.5h12v9l-4 4H4z"/><path d="M12 16.5v-4h4"/>',
  book: '<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H16v12H5.5A1.5 1.5 0 0 0 4 16.5z"/><path d="M4 16.5A1.5 1.5 0 0 0 5.5 18H16"/>',
  bookmark: '<path d="M6 3.5h8a1 1 0 0 1 1 1V17l-5-3.2L5 17V4.5a1 1 0 0 1 1-1z"/>',
  check: '<path d="m4.5 10.5 3.5 3.5 7.5-8"/>',
  minus: '<path d="M4 10h12"/>',
  fit: '<path d="M4 8V4h4M16 8V4h-4M4 12v4h4M16 12v4h-4"/>',
  external: '<path d="M11 4h5v5M16 4l-7 7M14 12v3a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h3"/>'
};

export function icon(name, size) {
  var wrap = document.createElement("span");
  wrap.innerHTML = '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"' +
    (size ? ' style="width:' + size + 'px;height:' + size + 'px"' : "") + ">" + (ICONS[name] || "") + "</svg>";
  return wrap.firstChild;
}

export function h(tag, attrs) {
  var el = document.createElement(tag);
  var key, value;
  for (key in attrs || {}) {
    value = attrs[key];
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") el.style.cssText = value;
    else if (key === "value") el.value = value;
    else if (key === "checked" || key === "disabled" || key === "selected") el[key] = !!value;
    else if (key.slice(0, 2) === "on" && typeof value === "function") el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  var children = Array.prototype.slice.call(arguments, 2).flat(Infinity);
  children.forEach(function (child) {
    if (child == null || child === false) return;
    el.append(child instanceof Node ? child : String(child));
  });
  return el;
}

export function iconButton(name, title, onClick, extra) {
  return h("button", Object.assign({ class: "icon-btn", title: title, "aria-label": title, onclick: onClick }, extra || {}), icon(name));
}

export function toast(message, bad) {
  var box = h("div", { class: "toast" + (bad ? " bad" : "") }, message);
  document.getElementById("toasts").append(box);
  setTimeout(function () { box.remove(); }, bad ? 5200 : 2800);
}

var openMenu = null;
export function closeMenu() {
  if (openMenu) { openMenu.remove(); openMenu = null; }
}

// items: [{label, icon, danger, onClick}] | "-" | {title}
export function showMenu(x, y, items) {
  closeMenu();
  var menu = h("div", { class: "menu", role: "menu" });
  items.forEach(function (item) {
    if (item === "-") { menu.append(h("hr")); return; }
    if (item.title) { menu.append(h("div", { class: "menu-title" }, item.title)); return; }
    menu.append(h("button", {
      role: "menuitem", class: item.danger ? "danger" : "", style: item.indent ? "padding-left:" + (9 + item.indent * 14) + "px" : null,
      onclick: function () { closeMenu(); item.onClick(); }
    }, item.icon ? icon(item.icon) : null, item.label));
  });
  document.body.append(menu);
  var rect = menu.getBoundingClientRect();
  menu.style.left = Math.min(x, innerWidth - rect.width - 8) + "px";
  menu.style.top = Math.min(y, innerHeight - rect.height - 8) + "px";
  openMenu = menu;
  setTimeout(function () {
    document.addEventListener("mousedown", function away(event) {
      if (!menu.contains(event.target)) { closeMenu(); }
      document.removeEventListener("mousedown", away, true);
    }, true);
  });
}

export function menuAt(element, items) {
  var rect = element.getBoundingClientRect();
  showMenu(rect.left, rect.bottom + 4, items);
}

function modal(build) {
  return new Promise(function (resolve) {
    var backdrop = h("div", { class: "backdrop" });
    function done(value) { backdrop.remove(); document.removeEventListener("keydown", onKey, true); resolve(value); }
    function onKey(event) { if (event.key === "Escape") { event.stopPropagation(); done(null); } }
    backdrop.addEventListener("mousedown", function (event) { if (event.target === backdrop) done(null); });
    document.addEventListener("keydown", onKey, true);
    backdrop.append(build(done));
    document.body.append(backdrop);
    var focus = backdrop.querySelector("input, .btn.primary");
    if (focus) { focus.focus(); if (focus.select) focus.select(); }
  });
}

export function askText(options) {
  return modal(function (done) {
    var input = h("input", { class: "text", value: options.value || "", placeholder: options.placeholder || "" });
    function submit() { var value = input.value.trim(); if (value) done(value); }
    input.addEventListener("keydown", function (event) { if (event.key === "Enter" && !event.isComposing) submit(); });
    return h("div", { class: "dialog", role: "dialog" },
      h("h3", null, options.title), options.message ? h("p", null, options.message) : null, input,
      h("div", { class: "buttons" },
        h("button", { class: "btn", onclick: function () { done(null); } }, "취소"),
        h("button", { class: "btn primary", onclick: submit }, options.confirm || "확인")));
  });
}

export function confirmDialog(options) {
  return modal(function (done) {
    return h("div", { class: "dialog", role: "alertdialog" },
      h("h3", null, options.title), options.message ? h("p", null, options.message) : null,
      h("div", { class: "buttons" },
        h("button", { class: "btn", onclick: function () { done(false); } }, "취소"),
        h("button", { class: "btn primary" + (options.danger ? " danger" : ""), style: options.danger ? "background:var(--danger)" : null,
          onclick: function () { done(true); } }, options.confirm || "확인")));
  });
}

export function relativeTime(iso) {
  if (!iso) return "—";
  var then = new Date(iso), seconds = (Date.now() - then.getTime()) / 1000;
  if (seconds < 60) return "방금";
  if (seconds < 3600) return Math.floor(seconds / 60) + "분 전";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "시간 전";
  if (seconds < 86400 * 7) return Math.floor(seconds / 86400) + "일 전";
  return then.toLocaleDateString();
}

export function isMac() { return document.documentElement.dataset.platform === "mac"; }
export function modKey(event) { return isMac() ? event.metaKey : event.ctrlKey; }
export var MOD = isMac() ? "⌘" : "Ctrl+";

