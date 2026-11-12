"use client";

import { Suspense } from "react";
import { AssistantPage } from "@/components/assistant/assistant-page";

export default function Page() {
  // useSearchParams needs a Suspense boundary above it.
  return (
    <Suspense fallback={null}>
      <AssistantPage />
    </Suspense>
  );
}
