import { useMemo, useState, type ReactNode } from "react";

export type SortDir = "asc" | "desc";

export interface ColumnDef<T> {
  key: keyof T & string;
  label: string;
  numeric?: boolean;
  format?: (value: T[keyof T], row: T) => string;
  render?: (value: T[keyof T], row: T) => ReactNode;
  /** Optional explanation shown in a tooltip beside the column name. */
  help?: string;
}

interface Props<T> {
  columns: ColumnDef<T>[];
  rows: T[];
  pageSize?: number;
  /** Controlled mode: the server owns sorting and paging. Pass all six; `rows` is then the current page. */
  total?: number;
  page?: number;
  onPageChange?: (page: number) => void;
  sortKey?: string | null;
  sortDir?: SortDir;
  onSortChange?: (key: string, dir: SortDir) => void;
  loading?: boolean;
  emptyText?: string;
  toolbar?: ReactNode;
  /** Stable row identity for the key prop; falls back to the row's index within the current page. */
  rowKey?: (row: T, index: number) => string | number;
}

export function DataTable<T extends object>(props: Props<T>) {
  const { columns, rows, pageSize = 25, loading = false, emptyText = "No rows", toolbar, rowKey } = props;
  const controlled = props.onPageChange !== undefined;

  const [localSortKey, setLocalSortKey] = useState<string | null>(null);
  const [localSortDir, setLocalSortDir] = useState<SortDir>("asc");
  const [localPage, setLocalPage] = useState(0);

  const sortKey = controlled ? props.sortKey ?? null : localSortKey;
  const sortDir = controlled ? props.sortDir ?? "asc" : localSortDir;

  const sorted = useMemo(() => {
    if (controlled || !sortKey) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey as keyof T];
      const bv = b[sortKey as keyof T];
      // Missing values sort last whichever way the column is pointing, so an unavailable row never
      // pushes a real value off the top of the table.
      const aMissing = av === null || av === undefined;
      const bMissing = bv === null || bv === undefined;
      if (aMissing || bMissing) return aMissing && bMissing ? 0 : aMissing ? 1 : -1;
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [controlled, rows, sortKey, sortDir]);

  const total = controlled ? props.total ?? rows.length : sorted.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(controlled ? props.page ?? 0 : localPage, pages - 1);
  const visible = controlled ? rows : sorted.slice(current * pageSize, (current + 1) * pageSize);

  const setPage = (p: number) => (controlled ? props.onPageChange?.(p) : setLocalPage(p));
  const toggleSort = (key: string) => {
    if (loading) return;
    const dir: SortDir = sortKey === key && sortDir === "asc" ? "desc" : "asc";
    if (controlled) props.onSortChange?.(key, dir);
    else { setLocalSortKey(key); setLocalSortDir(dir); setLocalPage(0); }
  };

  return (
    <div>
      {toolbar && <div className="toolbar">{toolbar}</div>}
      <div style={{ overflowX: "auto" }}>
        <table className="data">
          <thead>
            <tr>
              {columns.map((c) => {
                const active = sortKey === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    className={`${c.numeric ? "num " : ""}${active ? "sorted" : ""}`}
                    aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <span className="th-content">
                      <button type="button" className="th-sort" onClick={() => toggleSort(c.key)} disabled={loading} aria-label={`Sort by ${c.label}`}>
                        {c.label}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                      </button>
                      {c.help && <button type="button" className="help help--small help--down" aria-label={c.help} data-tip={c.help}>?</button>}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={columns.length} className="note" aria-live="polite">Loading…</td></tr>}
            {!loading && visible.length === 0 && (
              <tr><td colSpan={columns.length} className="note">{emptyText}</td></tr>
            )}
            {!loading && visible.map((row, i) => (
              <tr key={rowKey ? rowKey(row, i) : i}>
                {columns.map((c) => {
                  const value = row[c.key];
                  const content = c.render ? c.render(value, row) : c.format ? c.format(value, row) : String(value);
                  return <td key={c.key} className={c.numeric ? "num" : undefined}>{content}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-footer">
        <span className="table-footer__counts" aria-live="polite">
          <span>Rows on this page: {visible.length === 0 ? "0" : `${(current * pageSize + 1).toLocaleString()}–${(current * pageSize + visible.length).toLocaleString()}`}</span>
          <span>Total Rows: {total.toLocaleString()}</span>
        </span>
        {pages > 1 && (
          <span className="pager">
            <button onClick={() => setPage(current - 1)} disabled={loading || current === 0} aria-label="Previous page">Prev</button>
            <span className="current"> {current + 1} </span> / {pages}
            <button onClick={() => setPage(current + 1)} disabled={loading || current >= pages - 1} aria-label="Next page">Next</button>
          </span>
        )}
      </div>
    </div>
  );
}
