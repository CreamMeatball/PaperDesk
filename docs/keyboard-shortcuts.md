# Reader keyboard shortcuts

Select text in the original PDF, then press the key by itself:

| Key | Action |
| --- | --- |
| H | Highlight using the last selected color |
| C | Write a note about the selected passage |
| T | Translate |
| E | Explain |
| W | Define |
| Q or Enter | Quote the passage in the AI question composer |

These are single-letter shortcuts, not Command/Ctrl combinations. Command+C/Ctrl+C retains normal copy behavior. Command+F on macOS (Ctrl+F elsewhere) opens PDF find.

In the note editor, Command+Enter or Ctrl+Enter saves and Escape cancels. These keys do not save or close the editor while an input-method composition is active. The save button also shows its keyboard shortcut. Closing the editor returns focus to the prior control.

Letter shortcuts use physical key positions when `KeyboardEvent.code` is available, so the Korean input source does not change H into an unrecognized character. `event.key` remains a fallback for keyboards that omit `code`. Selection actions use the current PDF selection immediately rather than waiting for the floating toolbar's 180 ms delay. They do not reuse an older selection after it has collapsed, intercept text entry, or run while a dialog is open.

Run `node tests/browser/reader_shortcuts.cjs` with Playwright installed to test the browser interactions. The same optional `PAPERDESK_PLAYWRIGHT_MODULE` and `PAPERDESK_CHROMIUM` paths as `local_state.cjs` are supported. The test uses an isolated temporary library, offline demo responses, simulated Korean key events, real pointer selection and annotation persistence. It does not exercise a real macOS input source or WKWebView. Rebuild the frozen macOS app to include these source changes; an existing installed DMG does not read JavaScript from the NAS source checkout.

API references: [KeyboardEvent.code](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/code), [KeyboardEvent.isComposing](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/isComposing).

메모는 원문 옆에 떠 있는 창에서 편집합니다. 메모 핀을 다시 누르면 초안을 유지한 채 숨기거나 다시 표시하며, 제목 표시줄을 잡아 옮길 수 있습니다. PDF 하이라이트를 클릭하거나 우클릭하면 삭제 메뉴가 열립니다. macOS Paperdesk 메뉴의 Settings… 또는 ⌘,로 설정을 엽니다.
