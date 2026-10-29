"""Local Docling analysis, cached by PDF content and parser version."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from ..infrastructure.docling_worker import VERSION
LAYOUT_REVISION = 1


def normalize_docling(result: dict) -> dict:
    document = result["document"]
    pages = {int(n): {"number": int(n), "width": p["size"]["width"], "height": p["size"]["height"], "blocks": []}
             for n, p in document["pages"].items()}
    items = {item["self_ref"]: item for key in ("texts", "pictures", "tables", "groups") for item in document.get(key, [])}
    ranks = {}

    def visit(item):
        ref = item.get("self_ref", "")
        if ref in ranks:
            return
        ranks[ref] = len(ranks)
        for child in item.get("children", []):
            if child["$ref"] in items:
                visit(items[child["$ref"]])
    visit(document.get("body", {}))
    picture_children = {c["$ref"] for p in document.get("pictures", []) for c in p.get("children", [])}
    kinds = {"title": "title", "section_header": "heading", "caption": "caption", "formula": "equation",
             "picture": "figure", "table": "table", "page_header": "furniture", "page_footer": "furniture",
             "footnote": "footnote", "reference": "reference"}
    for collection in ("texts", "pictures", "tables"):
        for item in document.get(collection, []):
            label = item["label"]
            if item["self_ref"] in picture_children and label != "caption":
                continue
            text = item.get("text", item.get("orig", ""))
            for prov in item.get("prov", []):
                page = pages[prov["page_no"]]
                w, h, box = page["width"], page["height"], prov["bbox"]
                rect = [box["l"] / w, (h - box["t"]) / h, box["r"] / w, (h - box["b"]) / h] if box["coord_origin"] == "BOTTOMLEFT" else [box["l"] / w, box["t"] / h, box["r"] / w, box["b"] / h]
                rect = [max(0, min(1, float(v))) for v in rect]
                if rect[0] >= rect[2] or rect[1] >= rect[3]:
                    continue
                value = text or (None if label == "formula" else "")
                span = prov.get("charspan")
                if collection == "texts" and span and text:
                    start, end = span
                    value = text[start:end] if 0 <= start <= end <= len(text) else None
                page["blocks"].append({"ref": item["self_ref"], "rank": ranks.get(item["self_ref"], len(items)),
                                       "kind": kinds.get(label, "paragraph"), "text": value, "rect": rect,
                                       "captions": [c["$ref"] for c in item.get("captions", [])]})
    for page in pages.values():
        groups = [b for b in page["blocks"] if b["kind"] in ("figure", "table")]
        def inside_group(block):
            a = block["rect"]
            area = (a[2] - a[0]) * (a[3] - a[1])
            return any(g is not block and max(0, min(a[2], g["rect"][2]) - max(a[0], g["rect"][0])) *
                       max(0, min(a[3], g["rect"][3]) - max(a[1], g["rect"][1])) > area * .9 for g in groups)
        page["blocks"] = [b for b in page["blocks"] if b["kind"] in ("caption", "figure", "table") or not inside_group(b)]
        page["blocks"].sort(key=lambda b: (b["rank"], b["rect"][1], b["rect"][0]))
    return {"engine": "docling", "version": result["version"], "revision": LAYOUT_REVISION, "pages": sorted(pages.values(), key=lambda p: p["number"])}


WINDOWS = os.name == "nt"
# Windows Python and torch cannot start without SYSTEMROOT and the profile folders.
_CHILD_ENV = ("HOME", "PATH", "LANG", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
              *(("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
                 "PROGRAMDATA", "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE") if WINDOWS else ()))
# -I ignores PYTHONUTF8, so ask for UTF-8 mode on the command line (Korean Windows defaults to cp949); no console window.
_CHILD_FLAGS = ("-X", "utf8") if WINDOWS else ()
_CHILD_OPTIONS = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}


class LayoutAnalysis:
    def __init__(self, paths, library):
        self.paths, self.library = paths, library
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paperdesk-layout")
        self._states = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._process = None

    def _directory(self, doc_id):
        doc = self.library.get(doc_id)
        return self.paths.root / "layout-cache" / (doc.sha256 + "-docling-" + VERSION + "-" + str(LAYOUT_REVISION))

    def status(self, doc_id):
        directory = self._directory(doc_id)
        cache = directory / "layout.json"
        with self._lock:
            if cache.is_file():
                try:
                    result = json.loads(cache.read_text(encoding="utf-8"))
                    if result["version"] == VERSION and result.get("revision") == LAYOUT_REVISION:
                        return {"state": "completed", "layout": result}
                except (ValueError, KeyError):
                    pass
            state = dict(self._states.get(doc_id, {"state": "not_started"}))
            if state["state"] == "running":
                try:
                    state = json.loads((directory / "docling.status.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
            return state

    def summary(self, doc_id):
        if (self._directory(doc_id) / "layout.json").is_file():
            return {"doc_id": doc_id, "state": "completed"}
        return {"doc_id": doc_id, "state": self.status(doc_id)["state"]}

    def ensure(self, doc_id, retry=False):
        with self._lock:
            state = self.status(doc_id)
            if state["state"] in ("completed", "queued", "preparing", "running") or (state["state"] == "failed" and not retry):
                return state
            self._states[doc_id] = {"state": "queued"}
            self._pool.submit(self._run, doc_id)
            return {"state": "queued"}

    def _python(self):
        if getattr(sys, "frozen", False):
            if WINDOWS:  # Beside Paperdesk.exe in the installed folder.
                return Path(sys.executable).parent / "analysis-runtime" / "python.exe"
            return Path(sys.executable).parents[1] / "Resources" / "analysis-runtime" / "bin" / "python3.12"
        return Path(os.environ.get("PAPERDESK_ANALYSIS_PYTHON", sys.executable))

    def _run(self, doc_id):
        try:
            if self._stop.is_set():
                return
            directory = self._directory(doc_id)
            directory.mkdir(parents=True, exist_ok=True)
            self._states[doc_id] = {"state": "running"}
            worker = Path(__file__).parents[1] / "infrastructure" / "docling_worker.py"
            raw = directory / "docling.json"
            env = {k: v for k, v in os.environ.items() if k in _CHILD_ENV}
            env.update(PYTHONNOUSERSITE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")
            with (directory / "worker.log").open("w", encoding="utf-8") as log:
                with self._lock:
                    if self._stop.is_set():
                        return
                    self._process = subprocess.Popen([str(self._python()), "-B", "-I", *_CHILD_FLAGS, str(worker), str(self.library.pdf_path(doc_id)), str(raw), str(self.paths.root / "analysis-models")],
                                                     stdout=log, stderr=log, env=env, **_CHILD_OPTIONS)
                code = self._process.wait(timeout=1800)
            if code:
                raise RuntimeError("analysis_failed")
            result = normalize_docling(json.loads(raw.read_text(encoding="utf-8")))
            temporary = directory / "layout.tmp"
            temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            temporary.replace(directory / "layout.json")
            self._states[doc_id] = {"state": "completed"}
        except Exception:
            self._states[doc_id] = {"state": "failed", "error": "analysis_failed"}
        finally:
            with self._lock:
                if self._process and self._process.poll() is None:
                    self._process.kill()
                    self._process.wait()
                self._process = None

    def close(self):
        self._stop.set()
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
        self._pool.shutdown(wait=True, cancel_futures=True)
