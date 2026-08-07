import { cn } from "@/lib/utils";
import type { Hearing } from "@/types";

interface CauseListBadgeProps {
  hearing: Hearing;
  className?: string;
}

/** Where this matter sits in the court's published cause list.
 *
 * Shared by the hearing card and both calendar views so the four states
 * can never drift apart between them:
 *
 *   listed        -> "Item 3 · Court 1"  (the thing an advocate wants)
 *   not_published -> "Not yet listed"    (court hasn't posted -- absence
 *                                         means NOTHING yet)
 *   not_listed    -> "Not listed"        (list is out, matter isn't in it)
 *   not_checked   -> nothing rendered
 *
 * The middle two must never be collapsed: telling an advocate their
 * matter is "not listed" the evening before, purely because the court
 * hadn't published, is worse than saying nothing.
 */
export function CauseListBadge({ hearing, className }: CauseListBadgeProps) {
  const status = hearing.cause_list_status;
  if (!status || status === "not_checked") return null;

  const base =
    "text-[11px] font-semibold h-5 px-2 inline-flex items-center flex-shrink-0 whitespace-nowrap rounded-full";

  if (status === "listed") {
    const parts = [
      hearing.cause_list_item_number ? `Item ${hearing.cause_list_item_number}` : null,
      hearing.cause_list_court_hall ? `Court ${hearing.cause_list_court_hall}` : null,
    ].filter(Boolean);

    return (
      <span
        title={
          hearing.cause_list_stage
            ? `Cause list: ${hearing.cause_list_stage}`
            : "Listed in the court's cause list"
        }
        className={cn(base, "bg-[#e6f6ed] text-[#1d6b3f]", className)}
      >
        {parts.length > 0 ? parts.join(" · ") : "Listed"}
      </span>
    );
  }

  if (status === "not_published") {
    return (
      <span
        title="The court has not published the cause list for this date yet."
        className={cn(base, "bg-gray-100 text-[#4b5468]", className)}
      >
        Not yet listed
      </span>
    );
  }

  return (
    <span
      title="The cause list for this date is published and this matter is not in it."
      className={cn(base, "bg-[#fdf3e3] text-[#8a5a0b]", className)}
    >
      Not listed
    </span>
  );
}
