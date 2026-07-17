import { Skeleton } from "@/components/ui/skeleton";

export function CalendarSkeleton() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3.5">
        <div>
          <Skeleton className="h-8 w-32 mb-1.5" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-10 w-40 rounded-lg" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5 items-start">
        <div className="bg-white border border-gray-100 rounded-xl shadow-sm">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <Skeleton className="h-5 w-28" />
            <div className="flex gap-1.5">
              <Skeleton className="h-8 w-20 rounded-lg" />
              <Skeleton className="h-8 w-16 rounded-lg" />
            </div>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-7 gap-1.5">
              {Array.from({ length: 35 }).map((_, i) => (
                <Skeleton key={i} className="min-h-[58px] rounded-lg" />
              ))}
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-100 rounded-xl shadow-sm">
          <div className="px-5 py-4 border-b border-gray-100">
            <Skeleton className="h-4 w-40" />
          </div>
          <div className="p-4 flex flex-col gap-2.5">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
