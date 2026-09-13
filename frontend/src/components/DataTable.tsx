import { useMemo, useState, type ReactNode } from "react";

export type SortDir = "asc" | "desc";

export interface ColumnDef<T> {
  key: keyof T & string;
  label: string;
  numeric?: boolean;
  format?: (value: T[keyof T], row: T) => string;
  render?: (value: T[keyof T], row: T) => ReactNode;
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
}

export function DataTable<T extends object>(props: Props<T>) {
  const { columns, rows, pageSize = 25, loading = false, emptyText = "No rows", toolbar } = props;
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
                    className={`${c.numeric ? "num " : ""}${active ? "sorted" : ""}`}
                    aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <button type="button" className="th-sort" onClick={() => toggleSort(c.key)} aria-label={`Sort by ${c.label}`}>
                      {c.label}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                    </button>
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
              <tr key={i}>
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
        <span aria-live="polite">Total Rows: {total.toLocaleString()}</span>
        {pages > 1 && (
          <span className="pager">
            <button onClick={() => setPage(current - 1)} disabled={current === 0} aria-label="Previous page">Prev</button>
            <span className="current"> {current + 1} </span> / {pages}
            <button onClick={() => setPage(current + 1)} disabled={current >= pages - 1} aria-label="Next page">Next</button>
          </span>
        )}
      </div>
    </div>
  );
}
