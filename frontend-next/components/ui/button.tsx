import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = "primary", size = "md", disabled, ...props },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:-translate-y-px motion-reduce:hover:translate-y-0",
          {
            "bg-primary text-white hover:bg-primary-hover focus-visible:ring-primary":
              variant === "primary",
            "bg-white text-gray-800 border border-gray-200 hover:bg-gray-50 focus-visible:ring-gray-400":
              variant === "secondary",
            "bg-destructive text-white hover:bg-destructive-hover focus-visible:ring-destructive":
              variant === "danger",
            "bg-transparent text-gray-700 hover:bg-gray-100 focus-visible:ring-gray-400":
              variant === "ghost",
          },
          {
            // 44px-tall on mobile for a real touch target, reverting to the
            // compact desktop size at md+ (768px) where precise pointers are
            // the norm -- zero visual change above that breakpoint.
            "h-11 px-3 text-sm md:h-8": size === "sm",
            "h-11 px-4 text-sm md:h-10": size === "md",
            "h-12 px-6 text-base": size === "lg",
          },
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = "Button";
