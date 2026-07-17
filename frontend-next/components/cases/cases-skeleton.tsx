import { Skeleton } from "@/components/ui/skeleton";

export function CasesSkeleton() {
  return (
    <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-80 rounded-xl" />
        ))}
      </div>
    </div>
  );
}
