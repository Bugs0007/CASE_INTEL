"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { matchesCaseQuery, type DocCase } from "./model";

interface CaseComboboxProps {
  cases: DocCase[];
  value: number | null;
  onChange: (caseId: number | null) => void;
  className?: string;
}

const ALL = "All cases";

/** A case picker you can type into: matches the case title or its number. */
export function CaseCombobox({ cases, value, onChange, className }: CaseComboboxProps) {
  const id = useId();
  const listId = `${id}-list`;
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const selected = cases.find((c) => c.id === value) ?? null;
  const matches = useMemo(() => cases.filter((c) => matchesCaseQuery(c, query)), [cases, query]);
  // Row 0 is "All cases"; the cases follow.
  const count = matches.length + 1;

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent | TouchEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [open]);

  function choose(index: number) {
    onChange(index === 0 ? null : matches[index - 1].id);
    setQuery("");
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true);
      else setActive((a) => (a + 1) % count);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) setOpen(true);
      else setActive((a) => (a - 1 + count) % count);
    } else if (event.key === "Enter" && open) {
      event.preventDefault();
      choose(Math.min(active, count - 1));
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      setQuery("");
    } else if (event.key === "Tab") {
      setOpen(false);
      setQuery("");
    }
  }

  const label = selected ? `${selected.case_number} - ${selected.title}` : "";

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <input
        type="text"
        role="combobox"
        aria-label="Filter by case"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        value={open ? query : label}
        placeholder={open && selected ? label : ALL}
        title={label || undefined}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(e.target.value.trim() ? 1 : 0);
          setOpen(true);
        }}
        onKeyDown={onKeyDown}
        className="h-10 w-full overflow-hidden text-ellipsis rounded-lg border border-gray-200 bg-surface px-3 pr-8 text-sm placeholder:text-gray-800 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
      />
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Cases"
          className="absolute left-0 right-0 top-full z-[60] mt-1.5 max-h-72 min-w-[260px] overflow-y-auto rounded-lg border border-[var(--ci-ink-14)] bg-surface p-1.5 shadow-[0_12px_32px_rgba(10,20,40,0.22)]"
        >
          <Option id={`${id}-opt-0`} active={active === 0} selected={value === null} onPick={() => choose(0)} onHover={() => setActive(0)}>
            {ALL}
          </Option>
          {matches.map((c, i) => (
            <Option
              key={c.id}
              id={`${id}-opt-${i + 1}`}
              active={active === i + 1}
              selected={value === c.id}
              onPick={() => choose(i + 1)}
              onHover={() => setActive(i + 1)}
            >
              <span className="block truncate">{c.title}</span>
              <span className="block truncate font-mono text-[11.5px] text-gray-500">{c.case_number}</span>
            </Option>
          ))}
          {matches.length === 0 && <li role="presentation" className="px-2.5 py-2 text-[13px] text-gray-500">No case matches that.</li>}
        </ul>
      )}
    </div>
  );
}

function Option({
  id,
  active,
  selected,
  onPick,
  onHover,
  children,
}: {
  id: string;
  active: boolean;
  selected: boolean;
  onPick: () => void;
  onHover: () => void;
  children: React.ReactNode;
}) {
  return (
    <li
      id={id}
      role="option"
      aria-selected={selected}
      onMouseEnter={onHover}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPick}
      className={cn(
        "cursor-pointer rounded px-2.5 py-1.5 text-[13.5px] text-gray-900",
        active && "bg-[var(--ci-ink-08)]",
        selected && "font-semibold",
      )}
    >
      {children}
    </li>
  );
}
