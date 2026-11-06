/** Keyboard shortcuts for the app shell.
 *
 *   ⌘K / Ctrl+K   search          N   new case
 *   ?             this list       U   upload a document
 *
 * Plain letters are ignored while the user is typing or while a dialog is
 * open, so they never fire into a form field or a second dialog. */

export type ShortcutAction = "search" | "new-case" | "upload" | "shortcuts";

interface KeyLike {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  repeat?: boolean;
  defaultPrevented?: boolean;
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function shortcutFor(
  event: KeyLike,
  context: { typing: boolean; modalOpen: boolean },
): ShortcutAction | null {
  if (event.repeat || event.defaultPrevented) return null;

  // The search shortcut works from anywhere, including inside a field.
  if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === "k") {
    return "search";
  }

  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  if (context.typing || context.modalOpen) return null;

  if (event.key === "?") return "shortcuts";
  switch (event.key.toLowerCase()) {
    case "n":
      return "new-case";
    case "u":
      return "upload";
    default:
      return null;
  }
}

/** What the shortcuts dialog lists. */
export const SHORTCUT_LIST: { keys: string[]; label: string }[] = [
  { keys: ["N"], label: "New case" },
  { keys: ["U"], label: "Upload document" },
  { keys: ["⌘K", "Ctrl K"], label: "Search" },
  { keys: ["?"], label: "Show this list" },
];
