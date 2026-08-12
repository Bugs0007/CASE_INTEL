import type { Metadata } from "next";
import Link from "next/link";
import { WALKTHROUGH_ENABLED } from "@/lib/feature-flags";
import { WalkthroughClient } from "./walkthrough-client";

export const metadata: Metadata = {
  title: "Guided Tour - Case Intel",
  description: "A click-through tour of Case Intel with sample data. No real data is used or changed.",
};

export default function WalkthroughPage() {
  if (!WALKTHROUGH_ENABLED) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center px-4">
        <div className="text-center max-w-sm">
          <h1 className="text-xl mb-2">Tour unavailable</h1>
          <p className="text-sm text-gray-600 mb-4">
            The guided tour isn&apos;t turned on right now.
          </p>
          <Link href="/dashboard" className="ci-btn ci-btn--solid">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return <WalkthroughClient />;
}
