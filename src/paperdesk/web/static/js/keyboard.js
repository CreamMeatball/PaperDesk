// Letter shortcuts follow physical key positions even when the input source is Korean/Japanese.
// Fall back to key for accessibility keyboards and events that do not supply code.
export function shortcutKey(event) {
  if (/^Key[A-Z]$/.test(event.code || "")) return event.code.slice(3).toLowerCase();
  return (event.key || "").toLowerCase();
}

export function isTypingTarget(target) {
  return !!target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable ||
    !!(target.closest && target.closest('[role="textbox"]')));
}

export function dialogOpen() {
  return !!document.querySelector(".backdrop, dialog[open]");
}
