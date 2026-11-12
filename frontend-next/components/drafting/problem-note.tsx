import type { DraftProblem } from "./errors";

/** An inline error with its list of lines, as plain text. */
export function ProblemNote({ problem }: { problem: DraftProblem | null }) {
  if (!problem) return null;
  return (
    <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
      <p>{problem.message}</p>
      {problem.items.length > 0 && (
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {problem.items.map((item, index) => (
            <li key={index} className="break-words">
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
