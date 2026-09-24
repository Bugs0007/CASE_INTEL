"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Inbox, ScrollText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ClientMessageCard } from "@/components/client-updates/client-message-card";
import { useClientMessages, useSentMessages } from "@/hooks/use-clients";
import { cn, formatDate } from "@/lib/utils";
import type { ClientMessageKind } from "@/types";

type Tab = "drafts" | "sent";

const KIND_FILTERS: { value: ClientMessageKind | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "case_update", label: "Case updates" },
  { value: "payment_reminder", label: "Payment reminders" },
];

/** Client emails written by the system for the advocate to review and send
 * (case updates after an order or a new hearing date; payment reminders on
 * overdue invoices), plus the audit log of everything that went out.
 *
 * The tab lives in the URL (?tab=sent) so the sent log can be linked to. */
export default function MessagesPage() {
  // useSearchParams needs a Suspense boundary on a prerendered page.
  return (
    <Suspense fallback={null}>
      <Messages />
    </Suspense>
  );
}

function Messages() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "sent" ? "sent" : "drafts";
  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next === "drafts") params.delete("tab");
    else params.set("tab", next);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };
  const [kind, setKind] = useState<ClientMessageKind | "">("");

  const drafts = useClientMessages({ status: "draft", kind: kind || undefined }, tab === "drafts");
  const sent = useSentMessages();

  return (
    <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[900px] mx-auto">
      <div className="mb-5">
        <h1 className="text-page-title text-gray-900 mb-1.5">Client messages</h1>
        <p className="text-sm text-gray-600">
          Updates and reminders drafted for you. Nothing reaches a client until you press Send.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4" role="tablist">
        <TabButton active={tab === "drafts"} onClick={() => setTab("drafts")} icon={<Inbox className="h-4 w-4" />}>
          Drafts{drafts.data?.length ? ` (${drafts.data.length})` : ""}
        </TabButton>
        <TabButton active={tab === "sent"} onClick={() => setTab("sent")} icon={<ScrollText className="h-4 w-4" />}>
          Sent log
        </TabButton>
        {tab === "drafts" && (
          <div className="flex flex-wrap gap-1.5 sm:ml-auto" role="group" aria-label="Filter drafts">
            {KIND_FILTERS.map((f) => (
              <button
                key={f.value || "all"}
                type="button"
                onClick={() => setKind(f.value)}
                aria-pressed={kind === f.value}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors min-h-[36px]",
                  kind === f.value
                    ? "border-primary bg-primary text-page"
                    : "border-gray-200 bg-surface text-gray-700 hover:bg-gray-50",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {tab === "drafts" ? (
        drafts.isLoading ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : !drafts.data?.length ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-gray-500">
              No drafts waiting. New ones appear after an order is processed, a new hearing date is
              found, or an invoice goes unpaid past your reminder interval (set in{" "}
              <Link href="/settings" className="underline">Settings</Link>).
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {drafts.data.map((message) => (
              <ClientMessageCard key={message.id} message={message} showCase />
            ))}
          </div>
        )
      ) : sent.isLoading ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : !sent.data?.length ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-gray-500">Nothing sent yet.</CardContent>
        </Card>
      ) : (
        <Card>
          {/* Phones: one stacked row per message. As a table, To and
              Delivery -- whether it was actually emailed -- sat off-screen
              behind a sideways scroll at 375px. */}
          <ul className="md:hidden divide-y divide-gray-100" data-testid="sent-log-list">
            {sent.data.map((row) => (
              <li key={row.id} className="space-y-1 px-4 py-3 text-sm">
                <div className="text-gray-900">{row.subject}</div>
                <div className="text-xs text-gray-500">
                  {row.kind_display}
                  {row.case_number ? ` · ${row.case_number}` : ""}
                </div>
                <div className="break-words text-xs text-gray-700">To {row.to_emails.join(", ")}</div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span className={cn("ci-chip", row.delivery === "sent" ? "ci-chip--ok" : "ci-chip--pending")}>
                    {row.delivery === "sent" ? "Sent" : "Logged, not emailed"}
                  </span>
                  {formatDate(row.sent_at, "d MMM yyyy, HH:mm")}
                  {row.sent_by_username && ` · by ${row.sent_by_username}`}
                </div>
              </li>
            ))}
          </ul>
          <CardContent className="hidden md:block p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-gray-500 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-2 font-medium">When</th>
                  <th className="px-4 py-2 font-medium">What</th>
                  <th className="px-4 py-2 font-medium">To</th>
                  <th className="px-4 py-2 font-medium">Delivery</th>
                </tr>
              </thead>
              <tbody>
                {sent.data.map((row) => (
                  <tr key={row.id} className="border-b border-gray-50 align-top">
                    <td className="px-4 py-2 whitespace-nowrap text-gray-600">
                      {formatDate(row.sent_at, "d MMM yyyy, HH:mm")}
                      {row.sent_by_username && <div className="text-xs text-gray-400">by {row.sent_by_username}</div>}
                    </td>
                    <td className="px-4 py-2">
                      <div className="text-gray-900">{row.subject}</div>
                      <div className="text-xs text-gray-500">
                        {row.kind_display}
                        {row.case_number ? ` · ${row.case_number}` : ""}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-gray-700">{row.to_emails.join(", ")}</td>
                    <td className="px-4 py-2">
                      <span className={cn("ci-chip", row.delivery === "sent" ? "ci-chip--ok" : "ci-chip--pending")}>
                        {row.delivery === "sent" ? "Sent" : "Logged, not emailed"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium",
        active ? "bg-primary text-page" : "text-gray-700 hover:bg-gray-100",
      )}
    >
      {icon}
      {children}
    </button>
  );
}
