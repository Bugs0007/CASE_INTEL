"use client";

import { Toaster as SonnerToaster, toast } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast:
            "group border-gray-200 bg-white text-gray-900 shadow-lg rounded-lg font-sans",
          title: "text-sm font-medium",
          description: "text-sm text-gray-500",
          // Same three chip meanings as everywhere else -- "warning" and
          // "info" both fall outside ok/alert, so they share the pending
          // and neutral tokens respectively rather than getting their own
          // colors.
          success: "!border-status-ok !bg-status-ok-soft",
          error: "!border-status-alert !bg-status-alert-soft",
          warning: "!border-status-pending !bg-status-pending-soft",
          info: "!border-gray-200 !bg-gray-100",
        },
      }}
      closeButton
      richColors
    />
  );
}

// Re-export toast for easy imports
export { toast };

// Convenience wrappers
export const showToast = {
  success: (message: string, description?: string) =>
    toast.success(message, { description }),
  error: (message: string, description?: string) =>
    toast.error(message, { description }),
  warning: (message: string, description?: string) =>
    toast.warning(message, { description }),
  info: (message: string, description?: string) =>
    toast.info(message, { description }),
  loading: (message: string) => toast.loading(message),
  dismiss: (id?: string | number) => toast.dismiss(id),
  promise: <T,>(
    promise: Promise<T>,
    opts: {
      loading: string;
      success: string | ((data: T) => string);
      error: string | ((error: unknown) => string);
    },
  ) => toast.promise(promise, opts),
};
