"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import { useCreateCase } from "@/hooks/use-cases";
import { X, Briefcase } from "lucide-react";
import type { CaseType, CasePriority, CaseCreateInput } from "@/types";

interface CreateCaseDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

const CASE_TYPES: { value: CaseType; label: string }[] = [
  { value: "civil", label: "Civil" },
  { value: "criminal", label: "Criminal" },
  { value: "family", label: "Family" },
  { value: "corporate", label: "Corporate" },
  { value: "ip", label: "Intellectual Property" },
  { value: "labor", label: "Labor" },
  { value: "tax", label: "Tax" },
  { value: "other", label: "Other" },
];

const PRIORITIES: { value: CasePriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

export function CreateCaseDialog({
  isOpen,
  onClose,
  onSuccess,
}: CreateCaseDialogProps) {
  const createCase = useCreateCase();

  const [formData, setFormData] = useState<CaseCreateInput>({
    case_number: "",
    title: "",
    client_name: "",
    opposing_party: "",
    case_type: "civil",
    priority: "medium",
    filing_date: "",
    notes: "",
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const resetForm = useCallback(() => {
    setFormData({
      case_number: "",
      title: "",
      client_name: "",
      opposing_party: "",
      case_type: "civil",
      priority: "medium",
      filing_date: "",
      notes: "",
    });
    setErrors({});
  }, []);

  useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen, resetForm]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.case_number.trim()) {
      newErrors.case_number = "Case number is required";
    }
    if (!formData.title.trim()) {
      newErrors.title = "Title is required";
    }
    if (!formData.client_name.trim()) {
      newErrors.client_name = "Client name is required";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    try {
      await createCase.mutateAsync(formData);
      showToast.success(
        "Case created successfully",
        `Case ${formData.case_number} has been created.`,
      );
      onSuccess?.();
      onClose();
    } catch (error) {
      console.error("Failed to create case:", error);
      showToast.error("Failed to create case", "Please try again.");
      setErrors({ submit: "Failed to create case. Please try again." });
    }
  };

  const handleChange = (
    field: keyof CaseCreateInput,
    value: string | undefined,
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-case-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <Briefcase className="h-5 w-5 text-blue-600" />
            </div>
            <h2
              id="create-case-title"
              className="text-lg font-semibold text-gray-900"
            >
              Create New Case
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

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Case Number */}
          <div>
            <label
              htmlFor="case_number"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Case Number <span className="text-red-500">*</span>
            </label>
            <Input
              id="case_number"
              value={formData.case_number}
              onChange={(e) => handleChange("case_number", e.target.value)}
              placeholder="e.g., CASE-2024-001"
              className={errors.case_number ? "border-red-500" : ""}
            />
            {errors.case_number && (
              <p className="mt-1 text-sm text-red-500">{errors.case_number}</p>
            )}
          </div>

          {/* Title */}
          <div>
            <label
              htmlFor="title"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Title <span className="text-red-500">*</span>
            </label>
            <Input
              id="title"
              value={formData.title}
              onChange={(e) => handleChange("title", e.target.value)}
              placeholder="e.g., Smith vs. Johnson Property Dispute"
              className={errors.title ? "border-red-500" : ""}
            />
            {errors.title && (
              <p className="mt-1 text-sm text-red-500">{errors.title}</p>
            )}
          </div>

          {/* Client Name */}
          <div>
            <label
              htmlFor="client_name"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Client Name <span className="text-red-500">*</span>
            </label>
            <Input
              id="client_name"
              value={formData.client_name}
              onChange={(e) => handleChange("client_name", e.target.value)}
              placeholder="e.g., John Smith"
              className={errors.client_name ? "border-red-500" : ""}
            />
            {errors.client_name && (
              <p className="mt-1 text-sm text-red-500">{errors.client_name}</p>
            )}
          </div>

          {/* Opposing Party */}
          <div>
            <label
              htmlFor="opposing_party"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Opposing Party
            </label>
            <Input
              id="opposing_party"
              value={formData.opposing_party}
              onChange={(e) => handleChange("opposing_party", e.target.value)}
              placeholder="e.g., Jane Johnson"
            />
          </div>

          {/* Two Column Row: Case Type and Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="case_type"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Case Type
              </label>
              <Select
                id="case_type"
                value={formData.case_type}
                onChange={(e) =>
                  handleChange("case_type", e.target.value as CaseType)
                }
              >
                {CASE_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <label
                htmlFor="priority"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Priority
              </label>
              <Select
                id="priority"
                value={formData.priority}
                onChange={(e) =>
                  handleChange("priority", e.target.value as CasePriority)
                }
              >
                {PRIORITIES.map((priority) => (
                  <option key={priority.value} value={priority.value}>
                    {priority.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {/* Filing Date */}
          <div>
            <label
              htmlFor="filing_date"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Filing Date
            </label>
            <Input
              id="filing_date"
              type="date"
              value={formData.filing_date}
              onChange={(e) => handleChange("filing_date", e.target.value)}
            />
          </div>

          {/* Notes */}
          <div>
            <label
              htmlFor="notes"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Notes
            </label>
            <Textarea
              id="notes"
              value={formData.notes}
              onChange={(e) => handleChange("notes", e.target.value)}
              placeholder="Additional notes about the case..."
              rows={3}
              className="resize-none"
            />
          </div>

          {/* Submit Error */}
          {errors.submit && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{errors.submit}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={createCase.isPending}
            >
              {createCase.isPending ? "Creating..." : "Create Case"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
