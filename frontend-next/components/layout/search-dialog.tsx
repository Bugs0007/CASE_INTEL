"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { Briefcase, FileText, Search, User } from "lucide-react";
import { useCases } from "@/hooks/use-cases";
import { useClients } from "@/hooks/use-clients";
import { useDocuments } from "@/hooks/use-documents";
import { useModalLayer } from "@/hooks/use-modal-layer";
import { matchesQuery } from "@/lib/case-previews";
import { cn } from "@/lib/utils";

interface Hit {
  key: string;
  group: "Cases" | "Documents" | "Clients";
  title: string;
  subtitle: string;
  href: string;
}

const MAX_PER_GROUP = 5;
const GROUP_ICON = { Cases: Briefcase, Documents: FileText, Clients: User } as const;

/** Search across cases, documents and clients, from the top bar or ⌘K.
 *
 * It filters what the app already loads for those lists (the same calls the
 * Cases, Documents and Clients pages make) -- no search endpoint. Mounted
 * only while open, so those lists are not fetched until someone searches. */
export function SearchDialog({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  return isOpen ? <SearchPanel onClose={onClose} /> : null;
}

function SearchPanel({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  useModalLayer(panelRef, true);

  const cases = useCases("all");
  const documents = useDocuments();
  const clients = useClients();
  const loading = cases.isLoading || documents.isLoading || clients.isLoading;

  const hits = useMemo<Hit[]>(() => {
    if (!query.trim()) return [];
    const caseHits = (cases.data ?? [])
      .filter((c) =>
        matchesQuery(
          query,
          c.title,
          c.case_number,
          c.cnr_number,
          c.opposing_party,
          c.client_name,
          ...c.client_contacts.map((contact) => contact.name),
        ),
      )
      .slice(0, MAX_PER_GROUP)
      .map<Hit>((c) => ({
        key: `case-${c.id}`,
        group: "Cases",
        title: c.title,
        subtitle: c.case_number,
        href: `/cases/${c.id}`,
      }));
    const documentHits = (documents.data ?? [])
      .filter((d) => matchesQuery(query, d.filename, d.display_name, d.case?.title, d.case?.case_number))
      .slice(0, MAX_PER_GROUP)
      .map<Hit>((d) => ({
        key: `doc-${d.id}`,
        group: "Documents",
        title: d.display_name || d.filename,
        subtitle: d.case ? `${d.case.title} · ${d.case.case_number}` : "Not linked to a case",
        href: d.case_id ? `/cases/${d.case_id}?doc=${d.id}` : "/documents",
      }));
    const clientHits = (clients.data ?? [])
      .filter((c) => matchesQuery(query, c.name, c.email, c.phone))
      .slice(0, MAX_PER_GROUP)
      .map<Hit>((c) => ({
        key: `client-${c.id}`,
        group: "Clients",
        title: c.name,
        subtitle: `${c.case_count} case${c.case_count === 1 ? "" : "s"}`,
        href: "/clients",
      }));
    return [...caseHits, ...documentHits, ...clientHits];
  }, [query, cases.data, documents.data, clients.data]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function open(hit: Hit) {
    onClose();
    router.push(hit.href);
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && hits.length) {
      event.preventDefault();
      setActive((i) => (i + 1) % hits.length);
    } else if (event.key === "ArrowUp" && hits.length) {
      event.preventDefault();
      setActive((i) => (i - 1 + hits.length) % hits.length);
    } else if (event.key === "Enter" && hits[active]) {
      event.preventDefault();
      open(hits[active]);
    }
  }

  const activeId = hits[active] ? `search-hit-${hits[active].key}` : undefined;
  const groups = (["Cases", "Documents", "Clients"] as const)
    .map((group) => ({ group, hits: hits.filter((h) => h.group === group) }))
    .filter((g) => g.hits.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onMouseDown={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className="relative flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden rounded-lg border border-gray-200 bg-surface shadow-card"
      >
        <div className="flex items-center gap-2.5 border-b border-gray-100 px-4">
          <Search className="h-4 w-4 flex-shrink-0 text-gray-400" strokeWidth={1.8} />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded={hits.length > 0}
            aria-controls="search-results"
            aria-activedescendant={activeId}
            aria-label="Search cases, documents, clients"
            placeholder="Search cases, documents, clients"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onInputKeyDown}
            className="h-12 flex-1 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-400"
          />
          <kbd className="rounded-sm border border-gray-200 px-1.5 py-0.5 font-mono text-[11px] text-gray-500">Esc</kbd>
        </div>

        <div id="search-results" role="listbox" aria-label="Results" className="min-h-0 flex-1 overflow-y-auto py-1">
          {!query.trim() ? (
            <p className="px-4 py-6 text-sm text-gray-500">Type to search your cases, documents and clients.</p>
          ) : hits.length === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-500">
              {loading ? "Searching…" : `Nothing matches “${query.trim()}”.`}
            </p>
          ) : (
            groups.map(({ group, hits: groupHits }) => {
              const Icon = GROUP_ICON[group];
              return (
                <div key={group} role="group" aria-label={group}>
                  <div className="px-4 pb-1 pt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-gray-500">
                    {group}
                  </div>
                  {groupHits.map((hit) => {
                    const selected = hits[active]?.key === hit.key;
                    return (
                      <div
                        key={hit.key}
                        id={`search-hit-${hit.key}`}
                        role="option"
                        aria-selected={selected}
                        onMouseEnter={() => setActive(hits.indexOf(hit))}
                        onClick={() => open(hit)}
                        className={cn(
                          "flex cursor-pointer items-center gap-3 px-4 py-2",
                          selected ? "bg-[var(--ci-ink-08)]" : "",
                        )}
                      >
                        <Icon className="h-4 w-4 flex-shrink-0 text-gray-500" strokeWidth={1.8} />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-gray-900">{hit.title}</div>
                          <div className="truncate text-xs text-gray-500">{hit.subtitle}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <div className="border-t border-gray-100 px-4 py-2 text-xs text-gray-500">
          ↑ ↓ to move · Enter to open · Esc to close
        </div>
      </div>
    </div>
  );
}
