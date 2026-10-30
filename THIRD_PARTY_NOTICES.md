# Third-party software

| Component | Version | License | Where |
| --- | --- | --- | --- |
| [PDF.js](https://github.com/mozilla/pdf.js) | 4.10.38 | Apache-2.0 | src/paperdesk/web/static/vendor/pdfjs (license file included) |
| [marked](https://github.com/markedjs/marked) | 18.1.1 | MIT | src/paperdesk/web/static/vendor/marked.js |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.4.17 | Apache-2.0 or MPL-2.0 | src/paperdesk/web/static/vendor/purify.js |
| [KaTeX](https://github.com/KaTeX/KaTeX) | bundled | MIT | src/paperdesk/web/static/vendor/katex (fonts: woff2 only) |
| [pywebview](https://github.com/r0x0r/pywebview) | ≥5.3, optional | BSD-3-Clause | installed as a dependency for the native window |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) | via pywebview on macOS | MIT | installed as a dependency for the native window |

The application shell otherwise uses the Python standard library; document analysis uses the separate Docling runtime described below. The project's own license choice is tracked separately in docs/license-decision.md.

## Local Docling document analysis

Source installs install Docling into the app's Python environment from `requirements/docling-macos.lock` or `requirements/docling-windows.lock`. The pinned Heron model is downloaded on first analysis. The following notices apply to these components. Each component retains its upstream license; Paperdesk's own license remains Apache-2.0.

| Component | License | Upstream |
| --- | --- | --- |
| Docling code | MIT; copyright The Docling Contributors | https://github.com/docling-project/docling (license verified at v2.142.1) |
| Docling layout Heron model (`docling-project/docling-layout-heron`) | Apache-2.0 | https://huggingface.co/docling-project/docling-layout-heron |

### Docling — MIT License

Source: https://github.com/docling-project/docling/blob/v2.142.1/LICENSE

```text
MIT License

Copyright The Docling Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Docling layout Heron — Apache License 2.0

The upstream model card declares Apache-2.0: https://huggingface.co/docling-project/docling-layout-heron/blob/main/README.md.

The complete Apache License 2.0 text is included in the accompanying `LICENSE` file. Preserve any additional upstream copyright and NOTICE files supplied with the selected model revision. If upstream files are modified, retain the required modification notices.

These notices cover Docling code and the Heron layout model. Other dependencies and optional models retain their respective upstream licenses and notices.

Docling also installs PyTorch, Transformers, PDFium/pypdfium2 and the other dependencies pinned in those lock files; each keeps its license files in its `.dist-info` folder. The analysis does not use PyMuPDF.
