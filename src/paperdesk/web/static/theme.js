// Runs before first paint: theme (system/dark/light) and shell type (native window vs browser).
(function () {
  var root = document.documentElement;
  var choice = "system";
  var saved = window.paperdeskBoot && window.paperdeskBoot.preferences;  // from /boot.js (the app's database)
  if (saved && saved.theme) choice = saved.theme;
  function apply() {
    var dark = choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.dataset.themeChoice = choice;
    root.dataset.theme = dark ? "dark" : "light";
    native();
  }
  // macOS window: the translucent backdrop behind the page is drawn by the system, so it is told the theme too.
  function native() {
    var api = window.pywebview && window.pywebview.api;
    if (api && api.theme) api.theme(choice);
  }
  apply();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", apply);
  window.addEventListener("pywebviewready", native);
  window.paperdeskTheme = {
    get: function () { return choice; },
    set: function (value) {
      choice = value;
      if (saved) saved.theme = value;
      apply();
      window.dispatchEvent(new CustomEvent("paperdesk-preference", { detail: { theme: value } }));
    }
  };
  var params = new URLSearchParams(location.search);
  if (params.get("shell") === "native") { try { sessionStorage.setItem("paperdesk-shell", "native"); } catch (e) {} }
  var shell = "browser";
  try { shell = sessionStorage.getItem("paperdesk-shell") || "browser"; } catch (e) {}
  root.dataset.shell = shell;
  root.dataset.platform = /Mac/.test(navigator.platform) ? "mac" : "other";
})();
