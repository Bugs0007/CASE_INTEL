import { STATUS_LABEL, type ChipTone, type PracticeStatus } from "@/lib/dashboard/model";

/** The colour of each practice status. Navy / soft red / amber / soft blue /
 * warm grey, built from the theme's tokens where it has one. The theme has
 * no blue, so "new date from eCourts" carries its own. Colour is never the
 * only signal: every tile also says its reason in words. */
export const STATUS_COLOR: Record<PracticeStatus, string> = {
  today: "var(--ci-ink)",
  attn: "color-mix(in srgb, var(--ci-seal) 42%, white)",
  week: "color-mix(in srgb, var(--ci-warn) 50%, white)",
  ecourts: "#9db6dc",
  quiet: "var(--ci-paper-2)",
};

export function StatusSwatch({ status, className = "" }: { status: PracticeStatus; className?: string }) {
  return (
    <i
      aria-hidden="true"
      className={`inline-block flex-none rounded-[2px] ring-1 ring-inset ring-[var(--ci-ink-14)] ${className}`}
      style={{ background: STATUS_COLOR[status] }}
    />
  );
}

export function StatusChip({ status }: { status: PracticeStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-gray-700">
      <StatusSwatch status={status} className="h-2.5 w-2.5" />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function CauseChipView({ chip }: { chip: { label: string; tone: ChipTone } | null }) {
  if (!chip) return null;
  return <span className={`ci-chip ci-chip--${chip.tone} inline-flex flex-shrink-0 items-center`}>{chip.label}</span>;
}
