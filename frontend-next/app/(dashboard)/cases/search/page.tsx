"use client";

import { Suspense } from "react";
import { LegacyAdvocateSearch } from "@/components/advocate-search/legacy-search";
import { AdvocateSearchV2 } from "@/components/advocate-search/search-v2";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdvocateFeatures } from "@/hooks/use-advocate-search-v2";

// "Find cases by advocate". The redesigned page (profiles, a District courts and
// a High Courts tab, per-court status) is behind the server's ADVOCATE_SEARCH_V2
// flag: with it off, or the answer unavailable, the page that was here before
// loads, untouched (components/advocate-search/legacy-search.tsx).
function SearchSwitch() {
  const features = useAdvocateFeatures();
  if (features.isLoading) {
    return (
      <div className="px-6 pt-6" aria-busy="true">
        <Skeleton className="mb-3 h-8 w-72" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (features.data?.v2) return <AdvocateSearchV2 features={features.data} />;
  return <LegacyAdvocateSearch />;
}

export default function AdvocateSearchPage() {
  return (
    <Suspense fallback={null}>
      <SearchSwitch />
    </Suspense>
  );
}
