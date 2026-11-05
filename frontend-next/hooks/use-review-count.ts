import { useClientMessages } from "@/hooks/use-clients";

/** How many client messages are drafted and waiting for the advocate to
 * review -- the number on the sidebar's Messages tab. Shares the drafts
 * query the Messages page uses, so it costs one request, not two. */
export function useReviewCount(): number {
  const { data } = useClientMessages({ status: "draft" });
  return data?.length ?? 0;
}

/** "3", or "99+" past ninety-nine. */
export function formatBadge(count: number): string {
  return count > 99 ? "99+" : String(count);
}
