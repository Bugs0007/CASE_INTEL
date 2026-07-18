interface CollapseToggleProps {
  isOpen: boolean;
  onToggle: () => void;
  openLabel?: string;
  closedLabel?: string;
  className?: string;
}

/** Small text toggle button for collapsing a section's body while keeping
 * its header visible -- the pattern originally introduced on the Court
 * Tracking hearing-history table, now shared by any section that needs it. */
export function CollapseToggle({
  isOpen,
  onToggle,
  openLabel = "Collapse",
  closedLabel = "Expand",
  className = "",
}: CollapseToggleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`h-7 px-2.5 rounded-md border border-gray-200 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 ${className}`}
    >
      {isOpen ? openLabel : closedLabel}
    </button>
  );
}
