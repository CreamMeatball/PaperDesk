# Third-party software

| Component | Version | License | Where |
| --- | --- | --- | --- |
| [PDF.js](https://github.com/mozilla/pdf.js) | 4.10.38 | Apache-2.0 | src/paperdesk/web/static/vendor/pdfjs (license file included) |
| [marked](https://github.com/markedjs/marked) | 18.1.1 | MIT | src/paperdesk/web/static/vendor/marked.js |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.4.17 | Apache-2.0 or MPL-2.0 | src/paperdesk/web/static/vendor/purify.js |
| [KaTeX](https://github.com/KaTeX/KaTeX) | bundled | MIT | src/paperdesk/web/static/vendor/katex (fonts: woff2 only) |
| [pywebview](https://github.com/r0x0r/pywebview) | ≥5.3, optional | BSD-3-Clause | installed as a dependency for the native window |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) | via pywebview on macOS | MIT | installed as a dependency for the native window |
| [Sparkle](https://sparkle-project.org/) | Sparkle 2, selected at macOS release build time | MIT and included component notices | macOS release bundles only; framework and its distribution LICENSE are preserved |

Runtime application code otherwise uses the Python standard library. The optional macOS build uses PyInstaller (GPL with its application distribution exception); it is a build tool, not an application runtime dependency installed by the user.
