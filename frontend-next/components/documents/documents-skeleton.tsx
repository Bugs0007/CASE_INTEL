import { Skeleton } from "@/components/ui/skeleton";

export function DocumentsSkeleton() {
  return (
    <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
      <div className="flex items-center justify-between mb-[22px] flex-wrap gap-3">
        <div>
          <Skeleton className="h-8 w-36 mb-1.5" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-10 w-44 rounded-lg" />
      </div>

      <div className="mb-5 bg-white border border-gray-100 rounded-xl p-4">
        <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr_1fr_1fr] gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-10 rounded-lg" />
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[72px] rounded-[10px]" />
        ))}
      </div>
    </div>
  );
}
