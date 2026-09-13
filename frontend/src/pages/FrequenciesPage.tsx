import { useEffect, useState } from "react";
import { frequenciesCsvUrl, getFrequencies } from "../api";
import { Card } from "../components/Card";
import { DataTable, type ColumnDef, type SortDir } from "../components/DataTable";
import { PageHeader } from "../components/PageHeader";
import type { SummaryColumn, SummaryRow } from "../types";

const PAGE_SIZE = 50;

const COLUMNS: ColumnDef<SummaryRow>[] = [
  { key: "sample", label: "sample" },
  { key: "total_count", label: "total_count", numeric: true, format: (v) => Number(v).toLocaleString() },
  { key: "population", label: "population" },
  { key: "count", label: "count", numeric: true, format: (v) => Number(v).toLocaleString() },
  { key: "percentage", label: "percentage", numeric: true, format: (v) => Number(v).toFixed(2) },
];

export function FrequenciesPage() {
  const [rows, setRows] = useState<SummaryRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SummaryColumn>("sample");
  const [dir, setDir] = useState<SortDir>("asc");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput.trim()); setPage(0); }, 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getFrequencies({ search: search || undefined, sort, dir, limit: PAGE_SIZE, offset: page * PAGE_SIZE }, controller.signal)
      .then((r) => { setRows(r.rows); setTotal(r.total); setError(null); })
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, sort, dir, page]);

  const csvHref = frequenciesCsvUrl({ search: search || undefined, sort, dir });

  return (
    <>
      <PageHeader title="Cell frequencies" subtitle="Relative frequency of each immune cell population in every sample, as a percentage of the sample's total cell count." />
      <Card title="Population summary" subtitle="One row per population per sample. percentage = count / total_count x 100. Sorting, search and export cover all rows, not just the page shown.">
        {error && <p className="error">{error}</p>}
        <DataTable
          columns={COLUMNS}
          rows={rows}
          pageSize={PAGE_SIZE}
          total={total}
          page={page}
          onPageChange={setPage}
          sortKey={sort}
          sortDir={dir}
          onSortChange={(key, d) => { setSort(key as SummaryColumn); setDir(d); setPage(0); }}
          loading={loading}
          emptyText={search ? `No rows match "${search}"` : "No rows. Run make pipeline, then reload."}
          toolbar={
            <>
              <input type="search" placeholder="Search sample or population" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} aria-label="Search sample or population" />
              <a className="button" href={csvHref} download>Export CSV</a>
            </>
          }
        />
      </Card>
    </>
  );
}
