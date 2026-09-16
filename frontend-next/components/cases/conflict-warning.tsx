"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import type { ConflictHit } from "@/types";

interface ConflictWarningProps {
  conflicts: ConflictHit[];
  title: string;
  /** Actions (e.g. "Add case anyway") rendered under the list. */
  children?: ReactNode;
}

function whereItAppears(hit: ConflictHit): string {
  if (hit.kind === "role_unknown") return "a party (side not known) in";
  return hit.existing_side === "own" ? "your client in" : "the other side in";
}

/** Possible conflicts of interest between a new matter and existing cases.
 * A warning, never a block: names can match without being the same party. */
export function ConflictWarning({ conflicts, title, children }: ConflictWarningProps) {
  if (conflicts.length === 0) return null;

  return (
    <div
      role="alert"
      className="rounded-lg border border-status-pending bg-status-pending-soft p-3 text-sm text-gray-900"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5 text-status-pending" />
        <div className="min-w-0 space-y-2">
          <p className="font-medium">{title}</p>
          <ul className="space-y-1.5">
            {conflicts.map((hit) => (
              <li key={`${hit.case_id}-${hit.new_party}`} className="flex items-start gap-2">
                <span
                  className={`ci-chip flex-shrink-0 ${
                    hit.band === "likely" ? "ci-chip--alert" : "ci-chip--pending"
                  }`}
                >
                  {hit.band}
                </span>
                <span className="min-w-0">
                  <span className="font-medium">{hit.new_party}</span> resembles{" "}
                  <span className="font-medium">{hit.existing_party}</span>, {whereItAppears(hit)}{" "}
                  <Link href={`/cases/${hit.case_id}`} className="underline" target="_blank">
                    {hit.case_number}
                  </Link>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-gray-600">
            Names can match without being the same party. Check before taking the matter on.
          </p>
          {children}
        </div>
      </div>
    </div>
  );
}
