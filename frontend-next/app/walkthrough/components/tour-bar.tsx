"use client";

import { ArrowLeft, ArrowRight, RotateCcw, X } from "lucide-react";
import type { TourStep } from "../tour-steps";

interface TourBarProps {
  step: TourStep;
  index: number;
  total: number;
  onBack: () => void;
  onNext: () => void;
  onExit: () => void;
  onRestart: () => void;
}

export function TourBar({ step, index, total, onBack, onNext, onExit, onRestart }: TourBarProps) {
  const isFirst = index === 0;
  const isLast = index === total - 1;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[70] lg:pl-60">
      <div className="border-t border-[var(--ci-ink-14)] bg-[var(--ci-surface)] shadow-[0_-12px_30px_-20px_rgba(20,32,44,0.35)]">
        <div className="max-w-[900px] mx-auto px-4 sm:px-7 py-4">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0 flex-1">
              <div className="ci-eyebrow mb-1.5">
                Step {index + 1} of {total}
              </div>
              <h3 className="text-[19px] mb-1">{step.title}</h3>
              <p className="text-sm text-gray-700 max-w-[640px]">{step.caption}</p>
            </div>

            <div className="flex flex-col items-end gap-2 flex-shrink-0">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onExit}
                  className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors px-1"
                >
                  <X className="h-3.5 w-3.5" />
                  Skip tour
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onBack}
                  disabled={isFirst}
                  className="ci-btn ci-btn--line h-10 px-3.5 text-[13px] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </button>
                {isLast ? (
                  <button
                    type="button"
                    onClick={onRestart}
                    className="ci-btn ci-btn--solid h-10 px-4 text-[13px]"
                  >
                    <RotateCcw className="h-4 w-4" />
                    Restart tour
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={onNext}
                    className="ci-btn ci-btn--solid h-10 px-4 text-[13px]"
                  >
                    Next
                    <ArrowRight className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Progress dots */}
          <div className="flex items-center gap-1.5 mt-3.5">
            {Array.from({ length: total }).map((_, i) => (
              <span
                key={i}
                className="h-1.5 flex-1 rounded-full transition-colors"
                style={{
                  background: i <= index ? "var(--ci-seal)" : "var(--ci-ink-14)",
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
