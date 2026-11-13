import { Fragment, type ReactNode } from "react";

/** `**bold**` inside one line; everything else is plain text (React escapes it). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul"; items: string[] };

/** Paragraphs (split on blank lines), "- " bullet lists and **bold**: the only
 * formatting the practice assistant writes. No HTML is ever interpreted. */
export function AnswerText({ text }: { text: string }) {
  const blocks: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];
    if (!line.trim()) {
      blocks.push({ kind: "p", lines: [] });
    } else if (line.startsWith("- ")) {
      if (last?.kind === "ul") last.items.push(line.slice(2));
      else blocks.push({ kind: "ul", items: [line.slice(2)] });
    } else if (last?.kind === "p") {
      last.lines.push(line);
    } else {
      blocks.push({ kind: "p", lines: [line] });
    }
  }
  return (
    <div className="space-y-2 break-words text-sm text-gray-900">
      {blocks.map((block, i) =>
        block.kind === "ul" ? (
          <ul key={i} className="list-disc space-y-0.5 pl-5">
            {block.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </ul>
        ) : block.lines.length ? (
          <p key={i} className="whitespace-pre-wrap">
            {block.lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && "\n"}
                {inline(line)}
              </Fragment>
            ))}
          </p>
        ) : null,
      )}
    </div>
  );
}
