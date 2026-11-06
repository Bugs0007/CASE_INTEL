import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function CaseDetailSkeleton() {
  return (
    <>
      <MobileCaseSkeleton />
      <DesktopCaseSkeleton />
    </>
  );
}

/** A phone's shape: tabs, title block, the next-hearing card, quick actions. */
function MobileCaseSkeleton() {
  return (
    <div aria-hidden="true" className="px-4 pb-6 md:hidden">
      <div className="-mx-4 mb-3 flex h-[44px] items-center gap-6 border-b border-gray-200 bg-surface px-5">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className={`h-3 ${["w-14","w-12","w-[72px]","w-16"][i]}`} />
        ))}
      </div>
      <div className="flex gap-1.5">
        <Skeleton className="h-5 w-14 rounded-full" />
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-5 w-24" />
      </div>
      <Skeleton className="mt-3 h-7 w-4/5" />
      <Skeleton className="mt-2 h-7 w-3/5" />
      <Skeleton className="mt-4 h-[132px] w-full rounded-[3px]" />
      <div className="mt-3 flex gap-2 overflow-hidden">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-28 flex-none rounded-lg" />
        ))}
      </div>
      <Skeleton className="mt-4 h-5 w-32" />
      <Skeleton className="mt-3 h-[120px] w-full rounded-[3px]" />
      <Skeleton className="mt-3 h-[90px] w-full rounded-[3px]" />
    </div>
  );
}

function DesktopCaseSkeleton() {
  return (
    <div className="h-full overflow-hidden flex flex-col max-md:hidden">
      {/* Header */}
      <div className="bg-white border-b border-gray-100 px-7 py-5 flex-shrink-0">
        <Skeleton className="h-4 w-28 mb-3.5" />
        <div className="flex items-center justify-between mb-3.5 flex-wrap gap-2.5">
          <div className="flex items-center gap-2.5">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-4 w-24" />
          </div>
          <div className="flex items-center gap-2.5">
            <Skeleton className="h-9 w-20 rounded-lg" />
            <Skeleton className="h-9 w-32 rounded-lg" />
          </div>
        </div>
        <Skeleton className="h-7 w-2/5" />
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto min-[1100px]:flex min-[1100px]:overflow-hidden">
        {/* Main column: Order Overview, Hearings & Orders, Calendar */}
        <div className="min-w-0 min-[1100px]:flex-1 min-[1100px]:overflow-y-auto">
          <div className="px-4 sm:px-7 pt-6 pb-6 space-y-5">
            {["h-36", "h-28", "h-32"].map((height, i) => (
              <Card key={i}>
                <CardHeader className="flex flex-row items-center justify-between">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-9 w-32 rounded-lg" />
                </CardHeader>
                <CardContent className="space-y-3">
                  <Skeleton className={`w-full rounded-lg ${height}`} />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Side rail: Next hearing, Tasks, Case details, Documents, Fees, Contacts */}
        <div className="px-4 sm:px-7 pb-6 space-y-5 min-[1100px]:w-[400px] min-[1100px]:flex-shrink-0 min-[1100px]:overflow-y-auto min-[1100px]:border-l min-[1100px]:border-gray-100 min-[1100px]:px-5 min-[1100px]:pt-6">
          {["h-20", "h-24", "h-36", "h-24", "h-20", "h-16"].map((height, i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-36" />
              </CardHeader>
              <CardContent>
                <Skeleton className={`w-full rounded-lg ${height}`} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
