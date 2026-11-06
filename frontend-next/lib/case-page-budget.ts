/** How much of each card the case page can show for a window, so the page
 * never scrolls at 1280x760 and up.
 *
 * Rows are COUNTED, not clipped: a card renders exactly this many and the
 * rest sit behind its expand button. Below 1024px wide or under 700px tall
 * the page stops trying to fit and scrolls normally. */

export interface PageBudget {
  /** One fixed-height screen (no page scroll) rather than a scrolling page. */
  fit: boolean;
  hearingRows: number;
  documentRows: number;
  /** The same, when the Documents card also carries the order-check line
   * (a tracked case): the line takes the room of one row where the rail is
   * tight. */
  documentRowsWithCheck: number;
  /** Open tasks listed on the Tasks card before "n more". */
  taskRows: number;
  /** A mini month, or a 7-day strip when the window is short. */
  calendar: "month" | "week";
  /** Events and deadlines listed beside the calendar. */
  calendarItems: number;
  showClientUpdates: boolean;
  /** The rail's width in px. */
  railWidth: 352 | 320;
}

export const FIT_MIN_WIDTH = 1024;
export const FIT_MIN_HEIGHT = 700;

export function pageBudget(width: number, height: number): PageBudget {
  const railWidth = width >= 1400 ? 352 : 320;
  if (width < FIT_MIN_WIDTH || height < FIT_MIN_HEIGHT) {
    return {
      fit: false,
      hearingRows: 5,
      documentRows: 5,
      documentRowsWithCheck: 5,
      taskRows: 3,
      calendar: "month",
      calendarItems: 3,
      showClientUpdates: true,
      railWidth,
    };
  }
  if (height >= 881) {
    return { fit: true, hearingRows: 5, documentRows: 5, documentRowsWithCheck: 4, taskRows: 2, calendar: "month", calendarItems: 3, showClientUpdates: true, railWidth };
  }
  if (height >= 801) {
    return { fit: true, hearingRows: 4, documentRows: 4, documentRowsWithCheck: 4, taskRows: 2, calendar: "month", calendarItems: 3, showClientUpdates: false, railWidth };
  }
  return { fit: true, hearingRows: 3, documentRows: 3, documentRowsWithCheck: 2, taskRows: 1, calendar: "week", calendarItems: 2, showClientUpdates: false, railWidth };
}
