import { Skeleton } from "@/components/ui/skeleton";
import { CASES_TABS, SectionTabs } from "@/components/layout/section-tabs";

export function CasesSkeleton() {
  return (
    <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
      <SectionTabs tabs={CASES_TABS} />
      <div className="flex items-center justify-between mb-[22px] flex-wrap gap-3">
        <div>
          <Skeleton className="h-8 w-24 mb-1.5" />
          <Skeleton className="h-4 w-48" />
        </div>
        <Skeleton className="h-10 w-32 rounded-lg" />
      </div>

      <div className="mb-6 flex items-center justify-between gap-4 flex-wrap">
        <Skeleton className="h-10 w-80 rounded-lg" />
        <Skeleton className="h-10 w-[420px] rounded-lg" />
      </div>

      <div className="flex flex-col gap-px overflow-hidden rounded-xl">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="h-12 rounded-none" />
        ))}
      </div>
    </div>
  );
}
