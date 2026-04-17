export type PaginationSlice<T> = {
  items: T[];
  page: number;
  pageCount: number;
  total: number;
  start: number;
  end: number;
};

export function createDebouncedHandler<TArgs extends unknown[]>(
  callback: (...args: TArgs) => void,
  delay = 220,
): (...args: TArgs) => void {
  let timeoutId: number | null = null;
  return (...args: TArgs) => {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
    timeoutId = window.setTimeout(() => {
      timeoutId = null;
      callback(...args);
    }, delay);
  };
}

export function paginateItems<T>(
  items: T[],
  page: number,
  pageSize: number,
): PaginationSlice<T> {
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const nextPage = Math.min(Math.max(page, 1), pageCount);
  const start = total === 0 ? 0 : (nextPage - 1) * pageSize + 1;
  const end = Math.min(nextPage * pageSize, total);
  return {
    items: items.slice(start > 0 ? start - 1 : 0, end),
    page: nextPage,
    pageCount,
    total,
    start,
    end,
  };
}

export function updatePagerButtons(
  prevButton: Element | null,
  nextButton: Element | null,
  page: number,
  pageCount: number,
): void {
  if (prevButton instanceof HTMLButtonElement) {
    prevButton.disabled = page <= 1;
  }
  if (nextButton instanceof HTMLButtonElement) {
    nextButton.disabled = page >= pageCount;
  }
}

export function setPagerStatus(
  element: Element | null,
  options: {
    slice: PaginationSlice<unknown>;
    label: string;
    query: string;
  },
): void {
  if (!(element instanceof HTMLElement)) {
    return;
  }
  const { slice, label, query } = options;
  if (slice.total === 0) {
    element.textContent = query
      ? `No ${label} match \"${query}\".`
      : `No ${label} found.`;
    return;
  }
  const querySuffix = query ? ` · semantic search \"${query}\"` : "";
  element.textContent = `${slice.start}-${slice.end} of ${slice.total} ${label}${querySuffix}`;
}
