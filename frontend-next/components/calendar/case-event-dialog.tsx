"use client";

import { useEffect, useState } from "react";
import { CalendarPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import {
  useCreateCaseEvent,
  useDeleteCaseEvent,
  useUpdateCaseEvent,
} from "@/hooks/use-case-events";
import { apiErrorDetail } from "@/lib/api/client";
import type { CaseEvent, CaseEventStatus, CaseEventType } from "@/types";

interface CaseEventDialogProps {
  isOpen: boolean;
  onClose: () => void;
  caseId: number;
  /** Present -> edit this event. Absent -> create a new one. */
  event?: CaseEvent | null;
  /** YYYY-MM-DD to pre-fill a new event with (the day clicked on). */
  defaultDate?: string;
}

const EVENT_TYPES: { value: CaseEventType; label: string }[] = [
  { value: "arbitration", label: "Arbitration" },
  { value: "mediation", label: "Mediation" },
  { value: "client_meeting", label: "Client meeting" },
  { value: "client_call", label: "Client call" },
  { value: "internal_meeting", label: "Internal meeting" },
  { value: "site_visit", label: "Site visit" },
  { value: "filing", label: "Filing" },
  { value: "other", label: "Other" },
];

const EVENT_STATUSES: { value: CaseEventStatus; label: string }[] = [
  { value: "scheduled", label: "Scheduled" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

interface FormState {
  title: string;
  event_type: CaseEventType;
  date: string;
  allDay: boolean;
  start_time: string;
  end_time: string;
  location: string;
  notes: string;
  status: CaseEventStatus;
}

const EMPTY_FORM: FormState = {
  title: "",
  event_type: "other",
  date: "",
  allDay: true,
  start_time: "",
  end_time: "",
  location: "",
  notes: "",
  status: "scheduled",
};

/** Times come off the API as "HH:MM:SS"; <input type="time"> wants "HH:MM". */
const clock = (time: string | null) => (time ? time.slice(0, 5) : "");

export function CaseEventDialog({ isOpen, onClose, caseId, event, defaultDate }: CaseEventDialogProps) {
  const isEditing = !!event;
  const createEvent = useCreateCaseEvent();
  const updateEvent = useUpdateCaseEvent();
  const deleteEvent = useDeleteCaseEvent();
  const isBusy = createEvent.isPending || updateEvent.isPending || deleteEvent.isPending;

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  // Reset/pre-fill whenever the dialog opens or its target changes.
  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    if (event) {
      setForm({
        title: event.title,
        event_type: event.event_type,
        date: event.date,
        allDay: !event.start_time,
        start_time: clock(event.start_time),
        end_time: clock(event.end_time),
        location: event.location,
        notes: event.notes,
        status: event.status,
      });
    } else {
      setForm({ ...EMPTY_FORM, date: defaultDate ?? "" });
    }
  }, [isOpen, event, defaultDate]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const set = <K extends keyof FormState>(field: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.title.trim()) return setError("Give the event a title.");
    if (!form.date) return setError("Pick a date.");
    if (!form.allDay) {
      if (!form.start_time) return setError("Set a start time, or mark the event all-day.");
      if (form.end_time && form.end_time <= form.start_time) {
        return setError("The end time must be after the start time.");
      }
    }

    const payload = {
      title: form.title.trim(),
      event_type: form.event_type,
      date: form.date,
      start_time: form.allDay ? null : form.start_time,
      end_time: form.allDay || !form.end_time ? null : form.end_time,
      location: form.location.trim(),
      notes: form.notes.trim(),
      status: form.status,
    };

    try {
      if (event) {
        await updateEvent.mutateAsync({ id: event.id, data: payload });
        showToast.success("Event updated", "The event has been saved.");
      } else {
        await createEvent.mutateAsync({ case: caseId, ...payload });
        showToast.success("Event added", "It is on the case calendar.");
      }
      onClose();
    } catch (err) {
      console.error("Failed to save event:", err);
      const message = apiErrorDetail(err, "Please try again.");
      setError(message);
      showToast.error(isEditing ? "Update failed" : "Could not add event", message);
    }
  };

  const handleDelete = async () => {
    if (!event || !confirm("Delete this event?")) return;
    try {
      await deleteEvent.mutateAsync(event.id);
      showToast.success("Event deleted", "The event has been removed.");
      onClose();
    } catch (err) {
      console.error("Failed to delete event:", err);
      showToast.error("Delete failed", "Could not delete the event.");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />

      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="case-event-dialog-title"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gray-100 rounded-lg">
              <CalendarPlus className="h-5 w-5 text-gray-700" />
            </div>
            <h2 id="case-event-dialog-title" className="text-lg font-semibold text-gray-900">
              {isEditing ? "Edit Event" : "Add Event"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4" noValidate>
          <div>
            <label htmlFor="event_title" className="block text-sm font-medium text-gray-700 mb-1">
              Title <span className="text-status-alert">*</span>
            </label>
            <Input
              id="event_title"
              value={form.title}
              maxLength={200}
              onChange={(e) => set("title", e.target.value)}
              placeholder="e.g. Mediation sitting at the centre"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="event_type" className="block text-sm font-medium text-gray-700 mb-1">
                Type
              </label>
              <Select
                id="event_type"
                value={form.event_type}
                onChange={(e) => set("event_type", e.target.value as CaseEventType)}
              >
                {EVENT_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="event_date" className="block text-sm font-medium text-gray-700 mb-1">
                Date <span className="text-status-alert">*</span>
              </label>
              <Input
                id="event_date"
                type="date"
                value={form.date}
                onChange={(e) => set("date", e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="inline-flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.allDay}
                onChange={(e) => set("allDay", e.target.checked)}
              />
              All day
            </label>
            {!form.allDay && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
                <div>
                  <label htmlFor="event_start" className="block text-sm font-medium text-gray-700 mb-1">
                    Starts
                  </label>
                  <Input
                    id="event_start"
                    type="time"
                    value={form.start_time}
                    onChange={(e) => set("start_time", e.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="event_end" className="block text-sm font-medium text-gray-700 mb-1">
                    Ends <span className="font-normal text-gray-400">(optional)</span>
                  </label>
                  <Input
                    id="event_end"
                    type="time"
                    value={form.end_time}
                    onChange={(e) => set("end_time", e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          <div>
            <label htmlFor="event_location" className="block text-sm font-medium text-gray-700 mb-1">
              Location
            </label>
            <Input
              id="event_location"
              value={form.location}
              maxLength={255}
              onChange={(e) => set("location", e.target.value)}
              placeholder="An address or a meeting link"
            />
          </div>

          <div>
            <label htmlFor="event_notes" className="block text-sm font-medium text-gray-700 mb-1">
              Notes
            </label>
            <Textarea
              id="event_notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              rows={2}
              className="resize-none"
            />
          </div>

          <div>
            <label htmlFor="event_status" className="block text-sm font-medium text-gray-700 mb-1">
              Status
            </label>
            <Select
              id="event_status"
              value={form.status}
              onChange={(e) => set("status", e.target.value as CaseEventStatus)}
            >
              {EVENT_STATUSES.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </Select>
          </div>

          {error && (
            <div className="p-3 bg-status-alert-soft border border-status-alert-soft rounded-lg">
              <p className="text-sm text-status-alert">{error}</p>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 pt-4 border-t border-gray-100">
            <div>
              {isEditing && (
                <Button type="button" variant="ghost" onClick={handleDelete} disabled={isBusy}>
                  Delete
                </Button>
              )}
            </div>
            <div className="flex gap-3">
              <Button type="button" variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={isBusy}>
                {isBusy ? "Saving..." : isEditing ? "Save Changes" : "Add Event"}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
