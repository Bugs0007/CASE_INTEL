"use client";

import Link from "next/link";
import { Mail } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ClientMessageCard } from "@/components/client-updates/client-message-card";
import { useClientMessages } from "@/hooks/use-clients";

/** Client emails waiting for review on this case -- "heard on X, next date
 * Y" updates and payment reminders. Renders nothing when there are none,
 * like the fee card: it's a to-do, not a permanent section. */
export function CaseClientUpdatesCard({ caseId }: { caseId: number }) {
  const { data: drafts = [] } = useClientMessages({ case_id: caseId, status: "draft" });
  if (drafts.length === 0) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-4 w-4" />
          Client updates to review
          <span className="ci-chip ci-chip--pending">{drafts.length}</span>
        </CardTitle>
        <Link href="/messages" className="text-xs text-primary underline">
          All drafts
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-gray-500">
          Written for you from the latest order and hearing dates. Nothing is sent until you press Send.
        </p>
        {drafts.map((message) => (
          <ClientMessageCard key={message.id} message={message} />
        ))}
      </CardContent>
    </Card>
  );
}
