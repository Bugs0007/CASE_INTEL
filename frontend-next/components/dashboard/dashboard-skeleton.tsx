import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Shaped like the loaded dashboard: header row, then the Briefing card
 * beside its Glance column, so nothing jumps when the data arrives. */
export function DashboardSkeleton() {
  return (
    <>
      <MobileDashboardSkeleton />
      <DesktopDashboardSkeleton />
    </>
  );
}

/** A phone's shape: greeting, the number chips, the view switch and a few
 * hearing cards. Hidden from md up, where the desktop skeleton shows. */
function MobileDashboardSkeleton() {
  return (
    <div aria-hidden="true" className="px-4 pb-6 pt-4 md:hidden">
      <Skeleton className="h-7 w-56" />
      <Skeleton className="mt-2 h-4 w-40" />
      <Skeleton className="mt-2 h-3 w-60" />
      <div className="mt-4 flex gap-2 overflow-hidden">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[52px] w-[104px] flex-none rounded-[3px]" />
        ))}
      </div>
      <Skeleton className="mt-4 h-[46px] w-full rounded-[7px]" />
      <Skeleton className="mt-5 h-5 w-36" />
      {Array.from({ length: 2 }).map((_, i) => (
        <Skeleton key={i} className="mt-3 h-[118px] w-full rounded-[3px]" />
      ))}
      <Skeleton className="mt-5 h-5 w-28" />
      <Skeleton className="mt-3 h-[150px] w-full rounded-[3px]" />
    </div>
  );
}

function DesktopDashboardSkeleton() {
  return (
    <div data-testid="dashboard-skeleton" className="@container mx-auto hidden max-w-[1680px] px-4 pb-[60px] pt-5 sm:px-7 sm:pt-7 md:block">
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <div>
          <Skeleton className="mb-1.5 h-8 w-40" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-[250px] rounded-[7px]" />
        <Skeleton className="ml-auto h-9 w-52 rounded-lg" />
      </div>

      <div className="grid items-start gap-5 @[1000px]:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="px-5 py-7 @[1000px]:px-11">
          <Skeleton className="mb-3 h-9 w-72" />
          <Skeleton className="mb-7 h-6 w-96 max-w-full" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="border-t border-gray-100 py-5">
              <Skeleton className="mb-3 h-3 w-20" />
              <Skeleton className="mb-2 h-4 w-full max-w-[760px]" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
            </CardHeader>
            <CardContent className="space-y-2">
              {Array.from({ length: 14 }).map((_, i) => (
                <Skeleton key={i} className="h-3 w-full" />
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-28" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-16 w-full" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-20" />
            </CardHeader>
            <CardContent className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
