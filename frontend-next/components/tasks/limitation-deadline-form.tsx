"use client";

import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import {
  useAddLimitationDeadline,
  useLimitationCompute,
  useLimitationRules,
} from "@/hooks/use-limitation";
import { formatHearingDate } from "@/lib/utils";
import type { CourtType } from "@/types";

interface LimitationDeadlineFormProps {
  caseId: number;
  courtType: CourtType | null;
  /** The case's most recent dated order: the usual starting point. */
  latestOrder: { id: number; order_date: string } | null;
  onDone: () => void;
}

/** Pick a limitation rule and the date it runs from; the API computes the
 * last day (conservatively -- see the notes it returns) and records it as
 * a task. Nothing is recorded until "Add deadline". */
export function LimitationDeadlineForm({
  caseId,
  courtType,
  latestOrder,
  onDone,
}: LimitationDeadlineFormProps) {
  const { data: rules = [], isLoading: rulesLoading } = useLimitationRules(courtType);
  const [ruleKey, setRuleKey] = useState("");
  const [triggerDate, setTriggerDate] = useState(latestOrder?.order_date ?? "");
  const { data: computation, isFetching: computing } = useLimitationCompute(ruleKey, triggerDate);
  const addDeadline = useAddLimitationDeadline();

  const rule = rules.find((r) => r.key === ruleKey);
  // Link the deadline to the order it runs from, when that's what was picked.
  const sourceOrder =
    latestOrder && triggerDate === latestOrder.order_date ? latestOrder.id : null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ruleKey || !triggerDate) return;
    try {
      const result = await addDeadline.mutateAsync({
        caseId,
        data: { rule_key: ruleKey, trigger_date: triggerDate, source_order: sourceOrder },
      });
      showToast.success(
        result.outcome === "created" ? "Deadline added" : "Deadline already recorded",
        `Last day ${formatHearingDate(result.computation.last_day)}.`,
      );
      onDone();
    } catch (error) {
      console.error("Failed to add limitation deadline:", error);
      showToast.error("Could not add the deadline", "Try again in a moment.");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3"
    >
      <div className="grid grid-cols-1 @md:grid-cols-[1fr_11rem] gap-2">
        <div>
          <label htmlFor="limitation-rule" className="block text-xs text-gray-500 mb-1">
            What is being filed
          </label>
          <Select
            id="limitation-rule"
            value={ruleKey}
            onChange={(e) => setRuleKey(e.target.value)}
            disabled={rulesLoading}
          >
            <option value="">{rulesLoading ? "Loading…" : "Choose a limitation rule"}</option>
            {rules.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label} ({r.period_text})
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="limitation-trigger" className="block text-xs text-gray-500 mb-1">
            Runs from
          </label>
          <Input
            id="limitation-trigger"
            type="date"
            value={triggerDate}
            onChange={(e) => setTriggerDate(e.target.value)}
          />
        </div>
      </div>

      {rule && (
        <p className="text-xs text-gray-500">
          {rule.citation} · {rule.period_text} from {rule.runs_from}
          {sourceOrder !== null && " · counted from the latest order"}
        </p>
      )}

      {computation && (
        <div className="space-y-1.5 rounded-md bg-white p-3 border border-gray-100">
          <div className="text-sm text-gray-900">
            Last day:{" "}
            <span className="font-semibold font-mono">
              {formatHearingDate(computation.last_day)}
            </span>
            {computing && <Loader2 className="inline h-3.5 w-3.5 ml-2 animate-spin text-gray-400" />}
          </div>
          <ul className="list-disc pl-5 space-y-0.5 text-xs text-gray-600">
            {computation.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={!ruleKey || !triggerDate || !computation || addDeadline.isPending}
        >
          Add deadline
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
