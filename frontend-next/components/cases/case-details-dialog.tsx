"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import { useUpdateCase } from "@/hooks/use-cases";
import {
  useCreateClientContact,
  useDeleteClientContact,
  useUpdateClientContact,
} from "@/hooks/use-client-contacts";
import { X, FileEdit, Plus, Trash2 } from "lucide-react";
import { APIError } from "@/lib/api/client";
import type { Case, ContactRole, UserPartyRole } from "@/types";

interface CaseDetailsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  case: Case;
}

const PARTY_ROLES: { value: UserPartyRole; label: string }[] = [
  { value: "unknown", label: "Unknown" },
  { value: "petitioner", label: "Petitioner" },
  { value: "respondent", label: "Respondent" },
];

const CONTACT_ROLES: { value: ContactRole; label: string }[] = [
  { value: "primary", label: "Primary" },
  { value: "assistant", label: "Assistant" },
];

interface ContactRow {
  /** null for a row the advocate just added in this dialog -- not yet
   * persisted. Non-null rows are diffed against the case's original
   * client_contacts on Save to decide update vs. leave-alone. */
  id: number | null;
  /** Stable React key -- `contact-<id>` for existing rows, `new-<n>` for
   * ones added in this session (id is still null at that point). */
  key: string;
  name: string;
  email: string;
  phone: string;
  role: ContactRole;
  is_billing_contact: boolean;
}

let newRowCounter = 0;

function rowsFromCase(caseItem: Case): ContactRow[] {
  return caseItem.client_contacts.map((c) => ({
    id: c.id,
    key: `contact-${c.id}`,
    name: c.name,
    email: c.email || "",
    phone: c.phone || "",
    role: c.role,
    is_billing_contact: c.is_billing_contact,
  }));
}

export function CaseDetailsDialog({ isOpen, onClose, case: caseItem }: CaseDetailsDialogProps) {
  const updateCase = useUpdateCase();
  const createContact = useCreateClientContact();
  const updateContact = useUpdateClientContact();
  const deleteContact = useDeleteClientContact();

  const [title, setTitle] = useState("");
  const [opposingParty, setOpposingParty] = useState("");
  const [userPartyRole, setUserPartyRole] = useState<UserPartyRole>("unknown");
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setTitle(caseItem.title);
    setOpposingParty(caseItem.opposing_party || "");
    setUserPartyRole(caseItem.user_party_role);
    setContacts(rowsFromCase(caseItem));
  }, [isOpen, caseItem]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  function updateRow(key: string, patch: Partial<ContactRow>) {
    setContacts((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function handleAddContact() {
    setContacts((prev) => [
      ...prev,
      {
        id: null,
        key: `new-${newRowCounter++}`,
        name: "",
        email: "",
        phone: "",
        role: "primary",
        // First contact ever added defaults to the billing contact, so the
        // form always has exactly one selected once a row exists.
        is_billing_contact: prev.length === 0,
      },
    ]);
  }

  function handleRemoveContact(key: string) {
    setContacts((prev) => {
      const removed = prev.find((row) => row.key === key);
      const rest = prev.filter((row) => row.key !== key);
      if (removed?.is_billing_contact && rest.length > 0 && !rest.some((r) => r.is_billing_contact)) {
        rest[0] = { ...rest[0], is_billing_contact: true };
      }
      return rest;
    });
  }

  function handleSetBillingContact(key: string) {
    setContacts((prev) => prev.map((row) => ({ ...row, is_billing_contact: row.key === key })));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    if (contacts.some((row) => !row.name.trim())) {
      setError("Every client contact needs a name (or remove the empty row).");
      return;
    }

    setIsSaving(true);
    try {
      const originalById = new Map(caseItem.client_contacts.map((c) => [c.id, c]));
      const remainingIds = new Set(contacts.filter((r) => r.id !== null).map((r) => r.id));

      const ops: Promise<unknown>[] = [
        updateCase.mutateAsync({
          id: caseItem.id,
          data: {
            title: title.trim(),
            opposing_party: opposingParty.trim(),
            user_party_role: userPartyRole,
          },
        }),
      ];

      for (const row of contacts) {
        const contactData = {
          case: caseItem.id,
          name: row.name.trim(),
          email: row.email.trim() || undefined,
          phone: row.phone.trim() || undefined,
          role: row.role,
          is_billing_contact: row.is_billing_contact,
        };
        if (row.id === null) {
          ops.push(createContact.mutateAsync(contactData));
          continue;
        }
        const original = originalById.get(row.id);
        const changed =
          !original ||
          original.name !== row.name.trim() ||
          (original.email || "") !== row.email.trim() ||
          (original.phone || "") !== row.phone.trim() ||
          original.role !== row.role ||
          original.is_billing_contact !== row.is_billing_contact;
        if (changed) {
          ops.push(
            updateContact.mutateAsync({ id: row.id, caseId: caseItem.id, data: contactData }),
          );
        }
      }

      for (const original of caseItem.client_contacts) {
        if (!remainingIds.has(original.id)) {
          ops.push(deleteContact.mutateAsync({ id: original.id, caseId: caseItem.id }));
        }
      }

      await Promise.all(ops);
      showToast.success("Case details saved", "Title, contacts, and party role have been updated.");
      onClose();
    } catch (err) {
      console.error("Failed to save case details:", err);
      let message = "Please try again.";
      if (err instanceof APIError && err.data && typeof err.data === "object") {
        const payloadErr = err.data as Record<string, unknown>;
        const firstField = Object.keys(payloadErr)[0];
        if (firstField && Array.isArray(payloadErr[firstField]) && payloadErr[firstField][0]) {
          message = String(payloadErr[firstField][0]);
        }
      }
      setError(message);
      showToast.error("Could not save case details", message);
    } finally {
      setIsSaving(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="case-details-dialog-title"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <FileEdit className="h-5 w-5 text-blue-600" />
            </div>
            <h2 id="case-details-dialog-title" className="text-lg font-semibold text-gray-900">
              Edit Case Details
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

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <div>
            <label htmlFor="case-title" className="block text-sm font-medium text-gray-700 mb-1">
              Title <span className="text-red-500">*</span>
            </label>
            <Input
              id="case-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Smith Property Dispute"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="user-party-role" className="block text-sm font-medium text-gray-700 mb-1">
                Your Client&apos;s Side
              </label>
              <Select
                id="user-party-role"
                value={userPartyRole}
                onChange={(e) => setUserPartyRole(e.target.value as UserPartyRole)}
              >
                {PARTY_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="opposing-party" className="block text-sm font-medium text-gray-700 mb-1">
                Opposing Party <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <Input
                id="opposing-party"
                value={opposingParty}
                onChange={(e) => setOpposingParty(e.target.value)}
                placeholder="e.g., Jane Johnson"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="block text-sm font-medium text-gray-700">Client Contacts</span>
              <Button type="button" variant="secondary" size="sm" onClick={handleAddContact}>
                <Plus className="h-3.5 w-3.5" />
                Add Contact
              </Button>
            </div>

            {contacts.length === 0 && (
              <p className="text-sm text-gray-500 border border-dashed border-gray-200 rounded-lg px-3 py-4 text-center">
                No client contacts yet.
              </p>
            )}

            <div className="space-y-3">
              {contacts.map((row) => (
                <div key={row.key} className="border border-gray-100 rounded-lg p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="flex-1 grid grid-cols-2 gap-2">
                      <Input
                        aria-label="Contact name"
                        value={row.name}
                        onChange={(e) => updateRow(row.key, { name: e.target.value })}
                        placeholder="Name"
                      />
                      <Select
                        aria-label="Contact role"
                        value={row.role}
                        onChange={(e) => updateRow(row.key, { role: e.target.value as ContactRole })}
                      >
                        {CONTACT_ROLES.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </Select>
                      <Input
                        aria-label="Contact email"
                        type="email"
                        value={row.email}
                        onChange={(e) => updateRow(row.key, { email: e.target.value })}
                        placeholder="Email (optional)"
                      />
                      <Input
                        aria-label="Contact phone"
                        value={row.phone}
                        onChange={(e) => updateRow(row.key, { phone: e.target.value })}
                        placeholder="Phone (optional)"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveContact(row.key)}
                      className="p-2 text-gray-400 hover:text-destructive hover:bg-[#fdecec] rounded-lg transition-colors"
                      aria-label="Remove contact"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-gray-600">
                    <input
                      type="radio"
                      name="billing_contact"
                      checked={row.is_billing_contact}
                      onChange={() => handleSetBillingContact(row.key)}
                    />
                    Billing contact
                  </label>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={isSaving}>
              {isSaving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
