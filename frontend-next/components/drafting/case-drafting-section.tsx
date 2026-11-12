"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CASE_DRAFTING_ENABLED } from "@/lib/feature-flags";
import { CaseNotesSection } from "./case-notes-section";
import { DraftStudio } from "./draft-studio";

/** What the case page mounts: the entry point (flag on only), the studio
 * (its selected draft lives in ?draft=<id> so a reload reopens it) and the
 * saved notes. */
export function CaseDraftingSection({ caseId, caseTitle }: { caseId: number; caseTitle: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [opened, setOpened] = useState(false);

  const param = Number(searchParams.get("draft")) || null;
  const open = CASE_DRAFTING_ENABLED && (opened || param !== null);

  const setDraftParam = (id: number | null) => {
    const next = new URLSearchParams(searchParams.toString());
    if (id === null) next.delete("draft");
    else next.set("draft", String(id));
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  return (
    <div className="space-y-3">
      {CASE_DRAFTING_ENABLED && (
        <Button type="button" variant="secondary" size="sm" onClick={() => setOpened(true)}>
          <FileText className="h-4 w-4" aria-hidden="true" />
          Draft with assistant
        </Button>
      )}
      <CaseNotesSection caseId={caseId} />
      {CASE_DRAFTING_ENABLED && (
        <DraftStudio
          caseId={caseId}
          caseTitle={caseTitle}
          open={open}
          draftId={param}
          onSelect={setDraftParam}
          onClose={() => {
            setOpened(false);
            setDraftParam(null);
          }}
        />
      )}
    </div>
  );
}
