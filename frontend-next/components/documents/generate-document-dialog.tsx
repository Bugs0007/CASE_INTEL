"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FilePlus2, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import { useDocTemplatesForCase, useGenerateDocument } from "@/hooks/use-clients";
import { APIError, apiErrorDetail } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { Case, DocTemplateField } from "@/types";

interface GenerateDocumentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  caseItem: Case;
}

/** Vakalatnama, memo of appearance, cover letter -- merged from the case,
 * your profile and the client contact, no AI involved.
 *
 * Everything already on record is shown filled in; anything a template
 * needs that isn't on record gets a box here, for this document only
 * (nothing typed is saved back). Generation is refused while a required
 * field is empty, with the list of what's missing. */
export function GenerateDocumentDialog({ isOpen, onClose, caseItem }: GenerateDocumentDialogProps) {
  const [contactId, setContactId] = useState<number | null>(null);
  const [templateKey, setTemplateKey] = useState<string>("");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [serverMissing, setServerMissing] = useState<DocTemplateField[]>([]);

  const { data: templates = [], isLoading } = useDocTemplatesForCase(caseItem.id, contactId, isOpen);
  const generate = useGenerateDocument(caseItem.id);

  useEffect(() => {
    if (!isOpen) return;
    setInputs({});
    setServerMissing([]);
  }, [isOpen, templateKey, contactId]);

  useEffect(() => {
    if (isOpen && !templateKey && templates.length > 0) setTemplateKey(templates[0].key);
  }, [isOpen, templateKey, templates]);

  // The server picks a default contact (primary, then billing); mirror it.
  useEffect(() => {
    if (contactId === null && templates[0]?.contact_id) setContactId(templates[0].contact_id);
  }, [contactId, templates]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const template = templates.find((t) => t.key === templateKey);
  // Fields nothing on record can fill: these are the ones to type.
  const typedFields = useMemo(
    () => (template?.fields ?? []).filter((f) => !f.value),
    [template],
  );
  const stillMissing = typedFields.filter((f) => f.required && !(inputs[f.name] ?? "").trim());

  async function handleGenerate() {
    if (!template) return;
    setServerMissing([]);
    try {
      const document = await generate.mutateAsync({
        template: template.key,
        contact_id: contactId,
        inputs: Object.fromEntries(Object.entries(inputs).filter(([, v]) => v.trim())),
      });
      showToast.success(`${template.title} generated`, `Saved to this case's documents as ${document.filename}.`);
      onClose();
    } catch (error) {
      if (error instanceof APIError && (error.data as { code?: string })?.code === "missing_fields") {
        setServerMissing((error.data as { missing: DocTemplateField[] }).missing);
        return;
      }
      showToast.error("Could not generate the document", apiErrorDetail(error, "Please try again."));
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="generate-document-title"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gray-100 rounded-lg">
              <FilePlus2 className="h-5 w-5 text-gray-700" />
            </div>
            <h2 id="generate-document-title" className="text-lg font-semibold text-gray-900">
              Generate a document
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading templates…
            </div>
          ) : (
            <>
              <fieldset>
                <legend className="block text-sm font-medium text-gray-700 mb-2">Template</legend>
                <div className="grid gap-2 sm:grid-cols-3">
                  {templates.map((t) => (
                    <label
                      key={t.key}
                      className={cn(
                        "cursor-pointer rounded-lg border px-3 py-2 text-sm",
                        t.key === templateKey ? "border-primary bg-gray-50" : "border-gray-200",
                      )}
                    >
                      <input
                        type="radio"
                        name="template"
                        value={t.key}
                        checked={t.key === templateKey}
                        onChange={() => setTemplateKey(t.key)}
                        className="sr-only"
                      />
                      <span className="font-medium text-gray-900">{t.title}</span>
                      <span className={cn("ml-1 text-xs", t.ready ? "text-status-ok" : "text-gray-500")}>
                        {t.ready ? "ready" : ""}
                      </span>
                    </label>
                  ))}
                </div>
                {template && <p className="mt-2 text-xs text-gray-500">{template.description}</p>}
              </fieldset>

              {caseItem.client_contacts.length > 0 && (
                <div>
                  <label htmlFor="executant" className="block text-sm font-medium text-gray-700 mb-1">
                    Client contact (executant / addressee)
                  </label>
                  <Select
                    id="executant"
                    value={contactId ?? ""}
                    onChange={(e) => setContactId(e.target.value ? Number(e.target.value) : null)}
                  >
                    {caseItem.client_contacts.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </Select>
                </div>
              )}

              {template && (
                <div className="space-y-3">
                  <div>
                    <span className="block text-sm font-medium text-gray-700 mb-1">From your records</span>
                    <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2 text-sm">
                      {template.fields
                        .filter((f) => f.value)
                        .map((f) => (
                          <div key={f.name} className="min-w-0">
                            <dt className="text-xs text-gray-500">{f.label}</dt>
                            <dd className="text-gray-900 truncate" title={f.value}>
                              {f.value}
                            </dd>
                          </div>
                        ))}
                    </dl>
                  </div>

                  {typedFields.length > 0 && (
                    <div className="space-y-3">
                      <span className="block text-sm font-medium text-gray-700">
                        Not on record — fill in for this document
                      </span>
                      {typedFields.map((f) => (
                        <div key={f.name}>
                          <label htmlFor={`input-${f.name}`} className="block text-xs font-medium text-gray-700 mb-1">
                            {f.label}
                            {f.required ? <span className="text-status-alert"> *</span> : " (optional)"}
                          </label>
                          {f.multiline ? (
                            <Textarea
                              id={`input-${f.name}`}
                              rows={f.name === "body" ? 8 : 3}
                              value={inputs[f.name] ?? ""}
                              onChange={(e) => setInputs((prev) => ({ ...prev, [f.name]: e.target.value }))}
                            />
                          ) : (
                            <Input
                              id={`input-${f.name}`}
                              value={inputs[f.name] ?? ""}
                              onChange={(e) => setInputs((prev) => ({ ...prev, [f.name]: e.target.value }))}
                            />
                          )}
                          {f.where && (
                            <p className="mt-0.5 text-xs text-gray-400">
                              To keep it for next time, add it in {f.where}.
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {serverMissing.length > 0 && (
                <div className="p-3 bg-status-alert-soft border border-status-alert-soft rounded-lg" role="alert">
                  <p className="flex items-center gap-1.5 text-sm font-medium text-status-alert">
                    <AlertTriangle className="h-4 w-4" /> Still missing:
                  </p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-status-alert">
                    {serverMissing.map((m) => (
                      <li key={m.name}>
                        {m.label}
                        {m.where && <span className="text-xs"> — add it in {m.where}, or fill it in above</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
            {stillMissing.length > 0 && (
              <span className="mr-auto text-xs text-gray-500">
                {stillMissing.length} required field{stillMissing.length === 1 ? "" : "s"} to fill
              </span>
            )}
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleGenerate}
              disabled={!template || generate.isPending || stillMissing.length > 0}
            >
              {generate.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Generate PDF
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
