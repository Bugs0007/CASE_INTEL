import type { OrderSyncState } from "@/types";

/** How often the case page re-reads the case while an order check is queued
 * or running. Reads our own API only -- the portal is never involved. */
export const ORDER_SYNC_POLL_MS = 5000;

/** True while the worker has an order check for the case in hand. */
export function isOrderSyncActive(state: OrderSyncState | undefined | null): boolean {
  return state === "queued" || state === "running";
}
