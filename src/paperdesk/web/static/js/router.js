// History-API router. Routes: /library?folder=ID|all|recent|unfiled&q=..., /reader?id=..., /settings
export class Router extends EventTarget {
  constructor() {
    super();
    var self = this;
    window.addEventListener("popstate", function () { self.changed(); });
  }

  get route() {
    var url = new URL(location.href), q = url.searchParams;
    if (url.pathname === "/reader") return { name: "reader", id: q.get("id"), page: parseInt(q.get("page") || "1", 10) };
    if (url.pathname === "/settings") return { name: "settings", section: q.get("section") };
    return { name: "library", scope: q.get("folder") || "all", query: q.get("q") || "" };
  }

  go(path, replace) {
    if (path === location.pathname + location.search) return;
    history[replace ? "replaceState" : "pushState"]({}, "", path);
    this.changed();
  }

  changed() { this.dispatchEvent(new Event("change")); }
}

