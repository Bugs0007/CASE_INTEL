"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import { useCreateHearing, useUpdateHearing } from "@/hooks/use-hearings";
import { X, CalendarPlus } from "lucide-react";
import { APIError } from "@/lib/api/client";
import { toDatetimeLocal } from "@/lib/utils";
import type { Hearing, HearingStatus, HearingType } from "@/types";

interface HearingDialogProps {
  isOpen: boolean;
  onClose: () => void;
  caseId: number;
  /** Present -> edit this hearing. Absent -> create a new one. */
  hearing?: Hearing | null;
}

const HEARING_TYPES: { value: HearingType; label: string }[] = [
  { value: "preliminary", label: "Preliminary Hearing" },
  { value: "motion", label: "Motion Hearing" },
  { value: "trial", label: "Trial" },
  { value: "appeal", label: "Appeal" },
  { value: "sentencing", label: "Sentencing" },
  { value: "arraignment", label: "Arraignment" },
  { value: "status", label: "Status Conference" },
  { value: "other", label: "Other" },
];

const HEARING_STATUSES: { value: HearingStatus; label: string }[] = [
  { value: "scheduled", label: "Scheduled" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "postponed", label: "Postponed" },
];

const EMPTY_FORM = {
  hearing_date: "",
  hearing_type: "other" as HearingType,
  status: "scheduled" as HearingStatus,
  location: "",
  judge: "",
  notes: "",
  outcome: "",
};

export function HearingDialog({ isOpen, onClose, caseId, hearing }: HearingDialogProps) {
  const isEditing = !!hearing;
  const createHearing = useCreateHearing();
  const updateHearing = useUpdateHearing();
  const isSaving = createHearing.isPending || updateHearing.isPending;

  const [formData, setFormData] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  // Reset/pre-fill form whenever the dialog opens or the target hearing changes.
  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    if (hearing) {
      setFormData({
        hearing_date: toDatetimeLocal(hearing.hearing_date),
        hearing_type: hearing.hearing_type,
        status: hearing.status,
        location: hearing.location || "",
        judge: hearing.judge || "",
        notes: hearing.notes || "",
        outcome: hearing.outcome || "",
      });
    } else {
      setFormData(EMPTY_FORM);
    }
  }, [isOpen, hearing]);

  // Close on escape key
  useEffect(() => {
    if (typeof document === "undefined") return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const handleChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.hearing_date) {
      setError("Hearing date is required.");
      return;
    }

    // source is intentionally never sent -- the model defaults new hearings
    // to "manual", and editing an eCourts-sourced hearing here shouldn't
    // change its source either.
    const payload = {
      hearing_date: formData.hearing_date,
      hearing_type: formData.hearing_type,
      status: formData.status,
      location: formData.location || undefined,
      judge: formData.judge || undefined,
      notes: formData.notes || undefined,
      outcome: formData.outcome || undefined,
    };

    try {
      if (isEditing) {
        await updateHearing.mutateAsync({ id: hearing.id, data: payload });
        showToast.success("Hearing updated", "The hearing has been updated.");
      } else {
        await createHearing.mutateAsync({ case: caseId, ...payload });
        showToast.success("Hearing added", "The hearing has been scheduled.");
      }
      onClose();
    } catch (err) {
      console.error("Failed to save hearing:", err);
      let message = "Please try again.";
      if (err instanceof APIError && err.data && typeof err.data === "object") {
        const payloadErr = err.data as Record<string, unknown>;
        const firstField = Object.keys(payloadErr)[0];
        if (firstField && Array.isArray(payloadErr[firstField]) && payloadErr[firstField][0]) {
          message = String(payloadErr[firstField][0]);
        }
      }
      setError(message);
      showToast.error(isEditing ? "Update failed" : "Could not add hearing", message);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="hearing-dialog-title"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <CalendarPlus className="h-5 w-5 text-blue-600" />
            </div>
            <h2 id="hearing-dialog-title" className="text-lg font-semibold text-gray-900">
              {isEditing ? "Edit Hearing" : "Add Hearing"}
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

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label htmlFor="hearing_date" className="block text-sm font-medium text-gray-700 mb-1">
              Hearing Date &amp; Time <span className="text-red-500">*</span>
            </label>
            <Input
              id="hearing_date"
              type="datetime-local"
              value={formData.hearing_date}
              onChange={(e) => handleChange("hearing_date", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="hearing_type" className="block text-sm font-medium text-gray-700 mb-1">
                Type
              </label>
              <Select
                id="hearing_type"
                value={formData.hearing_type}
                onChange={(e) => handleChange("hearing_type", e.target.value)}
              >
                {HEARING_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="status" className="block text-sm font-medium text-gray-700 mb-1">
                Status
              </label>
              <Select
                id="status"
                value={formData.status}
                onChange={(e) => handleChange("status", e.target.value)}
              >
                {HEARING_STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div>
            <label htmlFor="judge" className="block text-sm font-medium text-gray-700 mb-1">
              Judge
            </label>
            <Input
              id="judge"
              value={formData.judge}
              onChange={(e) => handleChange("judge", e.target.value)}
              placeholder="e.g., Hon. Jane Doe"
            />
          </div>

          <div>
            <label htmlFor="location" className="block text-sm font-medium text-gray-700 mb-1">
              Location
            </label>
            <Input
              id="location"
              value={formData.location}
              onChange={(e) => handleChange("location", e.target.value)}
              placeholder="e.g., Courtroom 4B"
            />
          </div>

          <div>
            <label htmlFor="notes" className="block text-sm font-medium text-gray-700 mb-1">
              Notes
            </label>
            <Textarea
              id="notes"
              value={formData.notes}
              onChange={(e) => handleChange("notes", e.target.value)}
              placeholder="Purpose of hearing, preparation notes..."
              rows={2}
              className="resize-none"
            />
          </div>

          {isEditing && (
            <div>
              <label htmlFor="outcome" className="block text-sm font-medium text-gray-700 mb-1">
                Outcome
              </label>
              <Textarea
                id="outcome"
                value={formData.outcome}
                onChange={(e) => handleChange("outcome", e.target.value)}
                placeholder="What happened at this hearing..."
                rows={2}
                className="resize-none"
              />
            </div>
          )}

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
              {isSaving ? "Saving..." : isEditing ? "Save Changes" : "Add Hearing"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
