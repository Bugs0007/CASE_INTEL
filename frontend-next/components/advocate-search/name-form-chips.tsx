"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

const chip = "inline-flex h-7 items-center gap-1.5 rounded-full pl-3 pr-1.5 text-[13px] font-semibold";
const removeBtn =
  "grid h-[18px] w-[18px] place-items-center rounded-full text-gray-600 hover:bg-black/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

/** The spellings the advocate appears under, as removable chips, with the
 * suggested ones as dashed chips (added only when pressed) and a way to type
 * any other. */
export function NameFormChips({
  forms,
  suggestions,
  onRemove,
  onAdd,
  busy,
}: {
  forms: string[];
  suggestions: string[];
  onRemove: (name: string) => void;
  onAdd: (name: string) => void;
  busy?: boolean;
}) {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");

  const commit = () => {
    const name = draft.trim();
    if (name) onAdd(name);
    setDraft("");
    setTyping(false);
  };

  return (
    <ul className="flex flex-wrap items-start gap-1.5" aria-label="Names I appear under">
      {forms.map((name) => (
        <li key={name} className={cn(chip, "bg-gray-100 text-gray-900")}>
          {name}
          <button type="button" aria-label={`Remove ${name}`} className={removeBtn} disabled={busy} onClick={() => onRemove(name)}>
            <X className="h-3 w-3" />
          </button>
        </li>
      ))}
      {suggestions.map((name) => (
        <li key={`s-${name}`}>
          <button
            type="button"
            aria-label={`Add ${name}`}
            disabled={busy}
            onClick={() => onAdd(name)}
            className="inline-flex h-7 items-center rounded-full border border-dashed border-gray-400 bg-surface px-3 text-[13px] text-gray-700 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            + {name}
          </button>
        </li>
      ))}
      <li>
        {typing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commit();
              }
              if (e.key === "Escape") {
                setDraft("");
                setTyping(false);
              }
            }}
            onBlur={commit}
            aria-label="New name form"
            placeholder="As the court lists it"
            className="h-7 w-44 rounded-full border border-gray-400 bg-surface px-3 text-[13px] outline-none focus:ring-2 focus:ring-primary"
          />
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => setTyping(true)}
            className="inline-flex h-7 items-center rounded-full border border-dashed border-gray-400 bg-surface px-3 text-[13px] text-gray-700 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            + Add a name form
          </button>
        )}
      </li>
    </ul>
  );
}

/** The Not me list: spellings rejected from every search. */
export function NotMeChips({ names, onRemove, busy }: { names: string[]; onRemove: (name: string) => void; busy?: boolean }) {
  if (names.length === 0) return <p className="text-xs text-gray-500">Nothing rejected yet. Use Not me on a result row.</p>;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Not me">
      {names.map((name) => (
        <li key={name} className={cn(chip, "bg-status-alert-soft text-status-alert")}>
          {name}
          <button type="button" aria-label={`Remove ${name} from the Not me list`} className={removeBtn} disabled={busy} onClick={() => onRemove(name)}>
            <X className="h-3 w-3" />
          </button>
        </li>
      ))}
    </ul>
  );
}
