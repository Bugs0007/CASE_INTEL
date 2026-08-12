"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Gavel, FileText, Pencil, IndianRupee, MapPin, User, Plane, Send, CheckCircle2,
} from "lucide-react";
import { Spotlight } from "./spotlight";
import {
  mockCase, mockClientContacts, mockOrder, mockHearings, mockFeeSummary, mockInvoice,
} from "../mock-data";

export function CaseDetailScene({ highlight }: { highlight: string }) {
  return (
    <div className="max-w-[900px] mx-auto space-y-5 pb-4">
      {/* Header strip, purely decorative -- matches the real case detail header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="ci-eyebrow mb-1">{mockCase.caseNumber} · CNR {mockCase.cnr}</div>
          <h1 className="text-[28px]">{mockCase.title}</h1>
        </div>
        <span className="ci-chip ci-chip--ok">{mockCase.status}</span>
      </div>

      <Spotlight id="order-overview" active={highlight} className="block">
        <OrderOverview />
      </Spotlight>

      <Spotlight id="case-overview" active={highlight} className="block">
        <CaseOverview />
      </Spotlight>

      <Spotlight id="fees" active={highlight} className="block">
        <FeeSection />
      </Spotlight>

      <Card>
        <CardHeader>
          <CardTitle>Hearings & Deadlines (2)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {mockHearings.map((h) => (
            <HearingCard key={h.id} hearing={h} highlight={highlight} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function OrderOverview() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="flex items-center gap-2">
          <Gavel className="h-4 w-4" />
          Order Overview
          <span className="text-xs font-normal text-gray-400">{mockOrder.orderDate}</span>
        </CardTitle>
        <Button variant="secondary" size="sm" tabIndex={-1}>
          <FileText className="h-4 w-4" />
          Read the order
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-gray-800">{mockOrder.whatHappened}</p>

        <div className="space-y-3">
          <div className="rounded-lg border border-accent-soft bg-accent-soft p-3">
            <div className="text-xs font-semibold uppercase tracking-wide mb-1.5 text-accent">
              {mockOrder.yourSideLabel}
            </div>
            <ul className="space-y-1.5">
              {mockOrder.yourSideDirections.map((d, i) => (
                <li key={i} className="text-sm text-gray-800 flex gap-2">
                  <span className="text-gray-300 flex-shrink-0">•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-lg border border-gray-100 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide mb-1.5 text-gray-500">
              {mockOrder.otherSideLabel}
            </div>
            <ul className="space-y-1.5">
              {mockOrder.otherSideDirections.map((d, i) => (
                <li key={i} className="text-sm text-gray-800 flex gap-2">
                  <span className="text-gray-300 flex-shrink-0">•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="pt-3 border-t border-gray-100 text-sm">
          <span className="text-gray-500">Next date: </span>
          <span className="font-medium text-gray-900">{mockOrder.nextDate}</span>
          <span className="text-gray-500"> — {mockOrder.nextDatePurpose}</span>
        </div>
      </CardContent>
    </Card>
  );
}

const PARTY_LABEL: Record<string, string> = { Petitioner: "Petitioner", Respondent: "Respondent" };

function CaseOverview() {
  const fields = [
    { label: "Plaintiff/Client", value: mockClientContacts[0].name },
    { label: "Defendant/Opposing Party", value: mockCase.opposingParty },
    { label: "Your Client's Side", value: PARTY_LABEL[mockCase.yourSide] },
    { label: "Practice Area", value: mockCase.caseType },
    { label: "Case Status", value: mockCase.status },
    { label: "Priority", value: mockCase.priority },
    { label: "Filing Date", value: mockCase.filingDate },
  ];

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Case Overview</CardTitle>
        <Button variant="secondary" size="sm" tabIndex={-1}>
          <Pencil className="h-3.5 w-3.5" />
          Edit Details
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {fields.map((f) => (
            <div key={f.label} className="space-y-1">
              <dt className="text-xs text-gray-400 mb-1">{f.label}</dt>
              <dd className="text-sm text-gray-900 font-medium">{f.value}</dd>
            </div>
          ))}
        </div>

        <div className="mt-2 pt-4 border-t border-gray-100">
          <dt className="text-sm font-medium text-gray-500 mb-2">Client Contacts</dt>
          <dd>
            <ul className="space-y-1.5">
              {mockClientContacts.map((c) => (
                <li key={c.id} className="text-sm text-gray-700 flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-gray-900">{c.name}</span>
                  <span className="text-xs text-gray-400">{c.role}</span>
                  {c.isBilling && <span className="ci-chip ci-chip--none">Billing</span>}
                  {(c.email || c.phone) && (
                    <span className="text-xs text-gray-400">
                      {[c.email, c.phone].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </dd>
        </div>

        <div className="mt-2 pt-4 border-t border-gray-100">
          <dt className="text-sm font-medium text-gray-500 mb-2">Description</dt>
          <dd className="text-sm text-gray-700">{mockCase.notes}</dd>
        </div>
      </CardContent>
    </Card>
  );
}

type FeeState = "pending" | "invoiced" | "sent" | "paid";

function FeeSection() {
  // Purely local demo state -- there is no invoice_service, no PDF, no
  // email behind this. Clicking through pending -> invoiced -> sent -> paid
  // only ever calls setFeeState.
  const [feeState, setFeeState] = useState<FeeState>("pending");

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <IndianRupee className="h-4 w-4" />
            Appearance Fees
          </CardTitle>
          <div className="text-right">
            <div className="text-xs text-gray-400">Outstanding</div>
            <div className="text-sm font-semibold text-gray-900">{mockFeeSummary.outstanding}</div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <dt className="text-xs text-gray-400">Pending ({mockFeeSummary.pending.count})</dt>
              <dd className="text-sm font-semibold text-status-pending">{mockFeeSummary.pending.amount}</dd>
            </div>
            <div className="space-y-1">
              <dt className="text-xs text-gray-400">Invoiced ({mockFeeSummary.invoiced.count})</dt>
              <dd className="text-sm font-semibold text-status-pending">{mockFeeSummary.invoiced.amount}</dd>
            </div>
            <div className="space-y-1">
              <dt className="text-xs text-gray-400">Paid ({mockFeeSummary.paid.count})</dt>
              <dd className="text-sm font-semibold text-status-ok">{mockFeeSummary.paid.amount}</dd>
            </div>
          </div>
          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-sm">
            <span className="text-gray-500">Total billed on this case</span>
            <span className="font-medium text-gray-900">{mockFeeSummary.totalBilled}</span>
          </div>
        </CardContent>
      </Card>

      {/* Try it: the invoice lifecycle for the upcoming hearing's fee */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Try it — {mockInvoice.amount} fee for the {mockInvoice.hearingDate} hearing
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <StageChip label="Pending" active={feeState === "pending"} done={feeState !== "pending"} />
            <StageArrow />
            <StageChip
              label="Invoiced"
              active={feeState === "invoiced"}
              done={feeState === "sent" || feeState === "paid"}
            />
            <StageArrow />
            <StageChip label="Sent" active={feeState === "sent"} done={feeState === "paid"} />
            <StageArrow />
            <StageChip label="Paid" active={feeState === "paid"} done={false} />
          </div>

          {feeState === "sent" && (
            <div className="flex items-center gap-2 text-sm text-status-ok">
              <CheckCircle2 className="h-4 w-4" />
              Invoice {mockInvoice.number} emailed to {mockInvoice.billingContact} ({mockInvoice.billingEmail})
            </div>
          )}
          {feeState === "paid" && (
            <div className="flex items-center gap-2 text-sm text-status-ok">
              <CheckCircle2 className="h-4 w-4" />
              Marked paid — invoice {mockInvoice.number} settled
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            {feeState === "pending" && (
              <Button size="sm" onClick={() => setFeeState("invoiced")}>
                <FileText className="h-4 w-4" />
                Generate Invoice
              </Button>
            )}
            {feeState === "invoiced" && (
              <>
                <Button size="sm" onClick={() => setFeeState("sent")}>
                  <Send className="h-4 w-4" />
                  Send to Client
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setFeeState("paid")}>
                  Mark Paid
                </Button>
              </>
            )}
            {feeState === "sent" && (
              <Button size="sm" onClick={() => setFeeState("paid")}>
                Mark Paid
              </Button>
            )}
            {feeState === "paid" && (
              <Button variant="secondary" size="sm" onClick={() => setFeeState("pending")}>
                Reset demo
              </Button>
            )}
          </div>
          <p className="text-xs text-gray-400">
            This is a live demo of the three buttons — nothing here contacts a server, sends a
            real email, or creates a real PDF.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function StageChip({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span className={`ci-chip ${active || done ? "ci-chip--ok" : "ci-chip--none"}`}>{label}</span>
  );
}
function StageArrow() {
  return <span className="text-gray-300 text-xs">→</span>;
}

function HearingCard({
  hearing,
  highlight,
}: {
  hearing: (typeof mockHearings)[number];
  highlight: string;
}) {
  return (
    <div className="p-3.5 border border-gray-100 rounded-lg">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <div className="text-sm font-medium font-mono text-gray-900">{hearing.date}</div>
        <span className="ci-chip ci-chip--none">{hearing.type}</span>
        <span className="ci-chip ci-chip--none">{hearing.source}</span>
      </div>

      <div className="space-y-1">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <MapPin className="h-4 w-4" />
          <span>{hearing.location}</span>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <User className="h-4 w-4" />
          <span>{hearing.judge}</span>
        </div>
      </div>

      <div className="mt-2 flex items-center gap-2 flex-wrap">
        <span className={`ci-chip ${hearing.status === "Scheduled" ? "ci-chip--none" : "ci-chip--ok"}`}>
          {hearing.status}
        </span>

        <Spotlight id="cause-list" active={highlight} className="inline-block">
          <span
            className="ci-chip ci-chip--ok"
            title={`Cause list: item ${hearing.causeList.item}, court ${hearing.causeList.court}`}
          >
            Item {hearing.causeList.item} · Court {hearing.causeList.court}
          </span>
        </Spotlight>

        <span
          className={`ci-chip ${hearing.fee.status === "paid" ? "ci-chip--ok" : "ci-chip--pending"}`}
          title={hearing.fee.label}
        >
          {hearing.fee.amount} · {hearing.fee.status}
        </span>

        {hearing.travel && (
          <span className="ci-chip ci-chip--ok inline-flex items-center gap-1">
            <Plane className="h-3 w-3" />
            {hearing.travel.label}
          </span>
        )}
      </div>

      {hearing.orders.length > 0 && (
        <Spotlight id="hearing-orders" active={highlight} className="block mt-3">
          {hearing.orders.length > 1 && (
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Orders ({hearing.orders.length})
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {hearing.orders.map((o) => (
              <Button key={o.label} variant="secondary" size="sm" tabIndex={-1}>
                <FileText className="h-4 w-4" />
                {o.label}
              </Button>
            ))}
          </div>
        </Spotlight>
      )}
    </div>
  );
}
