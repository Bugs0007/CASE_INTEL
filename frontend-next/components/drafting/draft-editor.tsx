"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { EVIDENCE_KIND_LABEL, evidenceHref } from "./evidence-routes";
import type { DraftBlock, DraftBody, DraftEvidence } from "@/types/draft";

interface DraftEditorProps {
  body: DraftBody;
  evidence: DraftEvidence[];
  caseId: number;
  readOnly: boolean;
  onChange: (body: DraftBody) => void;
}

function replaceAt<T>(list: T[], index: number, value: T): T[] {
  return list.map((item, i) => (i === index ? value : item));
}

function removeAt<T>(list: T[], index: number): T[] {
  return list.filter((_, i) => i !== index);
}

/** Structured editor: title, section headings and blocks. Nothing here is
 * saved; edits go up through onChange and stay local until the advocate
 * saves a new version. */
export function DraftEditor({ body, evidence, caseId, readOnly, onChange }: DraftEditorProps) {
  const [inspected, setInspected] = useState<string | null>(null);
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));

  const setBlock = (si: number, bi: number, block: DraftBlock) =>
    onChange({
      ...body,
      sections: replaceAt(body.sections, si, {
        ...body.sections[si],
        blocks: replaceAt(body.sections[si].blocks, bi, block),
      }),
    });

  return (
    <div className="space-y-5">
      <div>
        <label htmlFor="draft-title" className="mb-1 block text-sm font-medium text-gray-800">
          Title
        </label>
        <Input
          id="draft-title"
          value={body.title}
          readOnly={readOnly}
          onChange={(e) => onChange({ ...body, title: e.target.value })}
        />
      </div>

      {body.sections.map((section, si) => (
        <section key={si} className="space-y-3" aria-label={`Section ${si + 1}`}>
          <div>
            <label htmlFor={`section-${si}-heading`} className="mb-1 block text-sm font-medium text-gray-800">
              {`Section ${si + 1} heading`}
            </label>
            <Input
              id={`section-${si}-heading`}
              value={section.heading}
              readOnly={readOnly}
              onChange={(e) =>
                onChange({ ...body, sections: replaceAt(body.sections, si, { ...section, heading: e.target.value }) })
              }
            />
          </div>

          {section.blocks.map((block, bi) => {
            const prefix = `Section ${si + 1} block ${bi + 1}`;
            const ids = block.evidence ?? [];
            const open = inspected !== null && ids.includes(inspected) ? evidenceById.get(inspected) : undefined;
            return (
              <div key={bi} className="min-w-0 rounded-lg border border-gray-200 p-3">
                {block.is_suggestion && (
                  <span className="mb-2 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                    Suggestion
                  </span>
                )}

                {block.type === "paragraph" && (
                  <Textarea
                    aria-label={`${prefix} paragraph`}
                    rows={4}
                    value={block.text}
                    readOnly={readOnly}
                    onChange={(e) => setBlock(si, bi, { ...block, text: e.target.value })}
                  />
                )}

                {block.type === "bullets" && (
                  <div className="space-y-2">
                    {block.items.map((item, ii) => (
                      <div key={ii} className="flex items-center gap-2">
                        <Input
                          aria-label={`${prefix} bullet ${ii + 1}`}
                          value={item}
                          readOnly={readOnly}
                          onChange={(e) => setBlock(si, bi, { ...block, items: replaceAt(block.items, ii, e.target.value) })}
                        />
                        {!readOnly && (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            aria-label={`${prefix} remove bullet ${ii + 1}`}
                            onClick={() => setBlock(si, bi, { ...block, items: removeAt(block.items, ii) })}
                          >
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                          </Button>
                        )}
                      </div>
                    ))}
                    {!readOnly && (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => setBlock(si, bi, { ...block, items: [...block.items, ""] })}
                      >
                        <Plus className="h-4 w-4" aria-hidden="true" />
                        {`Add bullet to ${prefix}`}
                      </Button>
                    )}
                  </div>
                )}

                {block.type === "table" && (
                  <div className="space-y-2">
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[20rem] border-collapse text-sm">
                        <thead>
                          <tr>
                            {block.columns.map((column, ci) => (
                              <th key={ci} scope="col" className="border-b border-gray-200 px-1 py-1 text-left font-semibold">
                                {column}
                              </th>
                            ))}
                            {!readOnly && <th className="w-10" aria-label="Row actions" />}
                          </tr>
                        </thead>
                        <tbody>
                          {block.rows.map((row, ri) => (
                            <tr key={ri}>
                              {block.columns.map((column, ci) => (
                                <td key={ci} className="px-1 py-1 align-top">
                                  <Input
                                    aria-label={`${prefix} row ${ri + 1} ${column}`}
                                    value={row[ci] ?? ""}
                                    readOnly={readOnly}
                                    onChange={(e) =>
                                      setBlock(si, bi, {
                                        ...block,
                                        rows: replaceAt(
                                          block.rows,
                                          ri,
                                          block.columns.map((_, k) => (k === ci ? e.target.value : (row[k] ?? ""))),
                                        ),
                                      })
                                    }
                                  />
                                </td>
                              ))}
                              {!readOnly && (
                                <td className="px-1 py-1 align-top">
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    aria-label={`${prefix} remove row ${ri + 1}`}
                                    onClick={() => setBlock(si, bi, { ...block, rows: removeAt(block.rows, ri) })}
                                  >
                                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                                  </Button>
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!readOnly && (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          setBlock(si, bi, { ...block, rows: [...block.rows, block.columns.map(() => "")] })
                        }
                      >
                        <Plus className="h-4 w-4" aria-hidden="true" />
                        {`Add row to ${prefix}`}
                      </Button>
                    )}
                  </div>
                )}

                {ids.length > 0 && (
                  <div className="mt-2">
                    <ul className="flex flex-wrap gap-1.5" aria-label={`${prefix} evidence`}>
                      {ids.map((id) => {
                        const item = evidenceById.get(id);
                        return (
                          <li key={id}>
                            <button
                              type="button"
                              aria-pressed={inspected === id}
                              onClick={() => setInspected(inspected === id ? null : id)}
                              className="max-w-full truncate rounded-full border border-gray-300 bg-gray-50 px-2.5 py-0.5 text-xs text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                            >
                              {item?.label ?? id}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                    {open && (
                      <div className="mt-2 rounded-lg bg-gray-50 p-3 text-sm" role="region" aria-label="Source">
                        <p className="break-words font-medium text-gray-900">{open.label}</p>
                        <p className="text-xs text-gray-600">{EVIDENCE_KIND_LABEL[open.kind] ?? open.kind}</p>
                        <a
                          href={evidenceHref(open, caseId)}
                          className="mt-1 inline-block text-primary underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        >
                          Open this record
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
