// UI language. Source strings are Korean and double as message ids (gettext style):
//   t("폴더를 찾지 못했어요.")  ·  t("{n}편 추가", { n: 3 })
// Catalogs live in /i18n/<code>.json and are shared with the Python server.

export var LANGUAGES = [["ko", "한국어"], ["en", "English"], ["ja", "日本語"], ["zh", "简体中文"]];
var SUPPORTED = LANGUAGES.map(function (l) { return l[0]; });
var catalog = null, current = "ko";

export function systemLocale() {
  var list = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"]);
  for (var i = 0; i < list.length; i++) {
    var code = String(list[i]).toLowerCase().split(/[-_]/)[0];
    if (SUPPORTED.indexOf(code) >= 0) return code;
  }
  return "en";
}

export function resolveLocale(choice) {
  return SUPPORTED.indexOf(choice) >= 0 ? choice : systemLocale();
}

export async function setLocale(choice) {
  var code = resolveLocale(choice);
  if (code === "ko") catalog = null;
  else {
    try {
      var response = await fetch("/i18n/" + code + ".json", { cache: "no-cache" });
      catalog = response.ok ? await response.json() : null;
    } catch (error) { catalog = null; }
  }
  current = catalog || code === "ko" ? code : "ko";
  document.documentElement.lang = current === "zh" ? "zh-Hans" : current;
  return current;
}

export function locale() { return current; }

export function t(text, vars) {
  var out = (catalog && catalog[text]) || text;
  if (!vars) return out;
  return out.replace(/\{(\w+)\}/g, function (match, key) { return vars[key] != null ? String(vars[key]) : match; });
}

