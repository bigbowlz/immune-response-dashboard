export type PageKey = "cohort" | "frequencies";

export const PAGES: Array<{ key: PageKey; label: string }> = [
  { key: "cohort", label: "Cohort analysis" },
  { key: "frequencies", label: "Cell frequencies" },
];

export function Sidebar({ active, generatedAt }: { active: PageKey; generatedAt?: string }) {
  return (
    <nav className="sidebar" aria-label="Sections">
      <div className="sidebar__brand"><span className="sidebar__mark" aria-hidden="true" />Immune Response Dashboard</div>
      <div className="sidebar__section">Analysis</div>
      {PAGES.map((item) => (
        <a
          key={item.key}
          href={`#/${item.key}`}
          className={`sidebar__item${item.key === active ? " sidebar__item--active" : ""}`}
          aria-current={item.key === active ? "page" : undefined}
        >
          {item.label}
        </a>
      ))}
      {generatedAt && (
        <div className="sidebar__footer">Pipeline run {new Date(generatedAt).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</div>
      )}
    </nav>
  );
}
