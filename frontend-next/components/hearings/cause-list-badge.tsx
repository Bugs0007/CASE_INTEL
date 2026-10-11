import { cn } from "@/lib/utils";
import type { Hearing } from "@/types";

interface CauseListBadgeProps {
  hearing: Hearing;
  className?: string;
}

/** Where this matter sits in the court's published cause list.
 *
 * Shared by the hearing card and both calendar views so the states can
 * never drift apart between them:
 *
 *   listed        -> "Item 3 · Court 1"   (the thing an advocate wants; the
 *                                          bench and list type are in the tip)
 *   not_published -> "Not yet listed"     (the court hasn't posted it, or not
 *                                          all of it -- absence means NOTHING)
 *   not_listed    -> "Not listed"         (the whole list is out and the
 *                                          matter isn't in it)
 *   fetch_failed  -> "Couldn't check"     (we could not get or read the list)
 *   unsupported   -> "Not covered"        (no source covers this court)
 *   not_checked   -> nothing rendered
 *
 * "Not listed", "Couldn't check" and "Not covered" must never be collapsed:
 * telling an advocate their matter is "not listed" when we simply could not
 * read the list, or do not cover the court, is worse than saying nothing.
 */
export function CauseListBadge({ hearing, className }: CauseListBadgeProps) {
  const status = hearing.cause_list_status;
  if (!status || status === "not_checked") return null;

  const base = "ci-chip inline-flex items-center flex-shrink-0";
  const note = hearing.cause_list_note ? ` ${hearing.cause_list_note}.` : "";

  if (status === "listed") {
    const parts = [
      hearing.cause_list_item_number ? `Item ${hearing.cause_list_item_number}` : null,
      hearing.cause_list_court_hall ? `Court ${hearing.cause_list_court_hall}` : null,
    ].filter(Boolean);
    const tip = [
      hearing.cause_list_bench ? `Bench: ${hearing.cause_list_bench}` : null,
      hearing.cause_list_list_type ? `List: ${hearing.cause_list_list_type}` : null,
      hearing.cause_list_stage ? `Stage: ${hearing.cause_list_stage}` : null,
    ].filter(Boolean);

    return (
      <span
        title={tip.length > 0 ? tip.join(" · ") : "Listed in the court's cause list"}
        className={cn(base, "ci-chip--ok", className)}
      >
        {parts.length > 0 ? parts.join(" · ") : "Listed"}
      </span>
    );
  }

  if (status === "not_published") {
    return (
      <span
        title={`The court has not published the cause list for this date yet.${note}`}
        className={cn(base, "ci-chip--none", className)}
      >
        Not yet listed
      </span>
    );
  }

  if (status === "fetch_failed") {
    return (
      <span
        title={`We could not read the court's cause list for this date, so we cannot say whether this matter is listed. It is retried on the next check.${note}`}
        className={cn(base, "ci-chip--alert", className)}
      >
        Couldn&apos;t check
      </span>
    );
  }

  if (status === "unsupported") {
    return (
      <span
        title={`Cause lists are not available for this court.${note}`}
        className={cn(base, "ci-chip--none", className)}
      >
        Not covered
      </span>
    );
  }

  return (
    <span
      title="The cause list for this date is published and this matter is not in it."
      className={cn(base, "ci-chip--pending", className)}
    >
      Not listed
    </span>
  );
}

/** The detail under the badge: every place a matter is listed (a main and a
 * supplementary list, say), the reason when we cannot say, and a link to
 * check the court's own site -- or, for the Supreme Court only, to the
 * published list itself. Renders nothing when there is nothing to add. */
export function CauseListInfo({ hearing }: { hearing: Hearing }) {
  const status = hearing.cause_list_status;
  if (!status || status === "not_checked") return null;

  const matches = hearing.cause_list_matches ?? [];
  const verify = hearing.cause_list_verify_url;
  const source = hearing.cause_list_source_url;

  const hasMatches = status === "listed" && matches.length > 0;
  const hasNote = Boolean(hearing.cause_list_note) && status !== "listed";
  if (!hasMatches && !hasNote && !source && !verify) return null;

  return (
    <div className="mt-1 text-xs text-gray-600" data-testid="cause-list-info">
      {hasMatches && (
        <ul className="space-y-0.5">
          {matches.map((m, i) => (
            <li key={i}>
              {[
                m.item_number && `Item ${m.item_number}`,
                m.court_hall && `Court ${m.court_hall}`,
                m.bench,
                m.list_type,
              ]
                .filter(Boolean)
                .join(" · ")}
            </li>
          ))}
        </ul>
      )}
      {hasNote && <p>{hearing.cause_list_note}</p>}
      {source ? (
        <a href={source} target="_blank" rel="noreferrer" className="inline-block underline">
          Open the published list
        </a>
      ) : (
        verify && (
          <a href={verify} target="_blank" rel="noreferrer" className="inline-block underline">
            Verify on the court&apos;s site
          </a>
        )
      )}
    </div>
  );
}
