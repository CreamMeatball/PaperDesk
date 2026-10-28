// Preferences are bootstrapped from the app database before first paint.
import { ApiClient } from "./api.js";
import { toast } from "./ui.js";
import { t } from "./i18n.js";

var values = Object.assign({}, (window.paperdeskBoot && window.paperdeskBoot.preferences) || {});
var api = new ApiClient(), writes = Promise.resolve(), pending = {};

export function pref(key, fallback) {
  return values[key] !== undefined ? values[key] : fallback;
}

export function setPref(key, value) {
  values[key] = value;
  pending[key] = value;
  return flushPrefs();
}

export function flushPrefs() {
  // Serialize writes so a slow earlier request cannot overwrite a later change.
  writes = writes.then(async function () {
    var body = pending;
    pending = {};
    if (!Object.keys(body).length) return;
    try { await api.request("PATCH", "/api/preferences", body, null, true); }
    catch (error) {
      pending = Object.assign({}, body, pending); // retry on the next change or pagehide
      toast(t("화면 설정을 저장하지 못했어요. 다시 시도해 주세요."), true);
    }
  });
  return writes;
}

window.addEventListener("pagehide", flushPrefs);
window.addEventListener("paperdesk-preference", function (event) {
  Object.keys(event.detail).forEach(function (key) { setPref(key, event.detail[key]); });
});

// Import old web-view storage once, deleting each old key only after a successful write.
// INSERT OR IGNORE on the app side preserves newer database values and deliberately cleared chats.
export async function migrateLegacy(api) {
  var map = { "paperdesk-theme": "theme", "paperdesk-sidebar": "sidebar", "paperdesk-assistant": "assistant",
    "paperdesk-tmode": "translation_mode", "paperdesk-nav": "navigator", "paperdesk-nav-tab": "navigator_tab",
    "paperdesk-hl": "highlight_color", "paperdesk-expanded": "expanded_folders" };
  var preferences = {}, keys = [], threads = [];
  try {
    Object.keys(map).forEach(function (old) {
      var value = localStorage.getItem(old);
      if (value === null) return;
      try { preferences[map[old]] = old === "paperdesk-expanded" ? JSON.parse(value) : value; keys.push(old); } catch (error) {}
    });
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      if (key && key.indexOf("paperdesk-thread:") === 0) {
        try {
          var turns = JSON.parse(localStorage.getItem(key));
          if (Array.isArray(turns)) threads.push({ key: key, id: key.slice("paperdesk-thread:".length), turns: turns });
        } catch (error) {}
      }
    }
  } catch (error) { return; } // localStorage can be disabled; it is not needed for normal operation
  try {
    if (keys.length) {
      var result = await api.post("/api/state/import", { preferences: preferences });
      Object.assign(values, result.preferences);
      window.paperdeskBoot.preferences = result.preferences;
      window.paperdeskTheme.set(values.theme);
      keys.forEach(function (key) { localStorage.removeItem(key); });
    }
    for (var j = 0; j < threads.length; j++) {
      var thread = threads[j], conversations = {};
      conversations[thread.id] = thread.turns;
      var imported = await api.post("/api/state/import", { conversations: conversations });
      if (imported.documents.indexOf(thread.id) >= 0) localStorage.removeItem(thread.key);
    }
  } catch (error) {
    toast(t("기존 기록을 옮기지 못했어요. 원래 기록은 보존되어 있어요."), true);
  }
}
