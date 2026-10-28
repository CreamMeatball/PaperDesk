// Runs before first paint: theme (system/dark/light) and shell type (native window vs browser).
(function () {
  var root = document.documentElement;
  var choice = "system";
  try { choice = localStorage.getItem("paperdesk-theme") || "system"; } catch (e) {}
  function apply() {
    var dark = choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.dataset.themeChoice = choice;
    root.dataset.theme = dark ? "dark" : "light";
  }
  apply();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", apply);
  window.paperdeskTheme = {
    get: function () { return choice; },
    set: function (value) { choice = value; try { localStorage.setItem("paperdesk-theme", value); } catch (e) {} apply(); }
  };
  var params = new URLSearchParams(location.search);
  if (params.get("shell") === "native") { try { sessionStorage.setItem("paperdesk-shell", "native"); } catch (e) {} }
  var shell = "browser";
  try { shell = sessionStorage.getItem("paperdesk-shell") || "browser"; } catch (e) {}
  root.dataset.shell = shell;
  root.dataset.platform = /Mac/.test(navigator.platform) ? "mac" : "other";
})();

