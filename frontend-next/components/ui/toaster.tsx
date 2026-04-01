"use client";

import { Toaster as SonnerToaster, toast } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast:
            "group border-gray-200 bg-white text-gray-900 shadow-lg rounded-lg",
          title: "text-sm font-medium",
          description: "text-sm text-gray-500",
          success: "!border-green-200 !bg-green-50",
          error: "!border-red-200 !bg-red-50",
          warning: "!border-yellow-200 !bg-yellow-50",
          info: "!border-blue-200 !bg-blue-50",
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
