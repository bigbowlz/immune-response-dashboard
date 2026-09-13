import { useEffect, useState } from "react";
import { ApiError, getHealth } from "./api";
import { Card } from "./components/Card";
import { PAGES, Sidebar, type PageKey } from "./components/Sidebar";
import { FrequenciesPage } from "./pages/FrequenciesPage";
import { ResponsePage } from "./pages/ResponsePage";
import { SubsetsPage } from "./pages/SubsetsPage";
import type { Health } from "./types";

const DEFAULT_PAGE: PageKey = "response";

function pageFromHash(): PageKey {
  const key = window.location.hash.replace(/^#\/?/, "");
  return PAGES.some((p) => p.key === key) ? (key as PageKey) : DEFAULT_PAGE;
}

type Gate = { state: "checking" } | { state: "ok"; health: Health } | { state: "no-data"; detail: string } | { state: "error"; detail: string };

export default function App() {
  const [page, setPage] = useState<PageKey>(pageFromHash);
  const [gate, setGate] = useState<Gate>({ state: "checking" });

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    if (!window.location.hash) window.location.replace(`#/${DEFAULT_PAGE}`);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    getHealth()
      .then((health) => {
        if ((health.tables.sample_summary ?? 0) === 0) setGate({ state: "no-data", detail: "The database exists but has no results yet." });
        else setGate({ state: "ok", health });
      })
      .catch((e: Error) => {
        if (e instanceof ApiError && e.status === 503) setGate({ state: "no-data", detail: e.detail });
        else if (e instanceof ApiError) setGate({ state: "error", detail: `The API answered ${e.status}: ${e.detail}. If the database predates a code change, run make pipeline again.` });
        else setGate({ state: "error", detail: `${e.message}. Start the server with make dashboard, or check the terminal where it is running.` });
      });
  }, []);

  const generatedAt = gate.state === "ok" ? gate.health.meta.generated_at : undefined;

  return (
    <div className="layout">
      <Sidebar active={page} generatedAt={generatedAt} />
      <main>
        {gate.state === "checking" && <p className="note" aria-live="polite">Connecting to the API…</p>}
        {gate.state === "no-data" && (
          <div className="notice">
            <Card title="No pipeline output found">
              <p>No pipeline output found. Run <code>make pipeline</code>, then reload.</p>
              <p>{gate.detail}</p>
            </Card>
          </div>
        )}
        {gate.state === "error" && (
          <Card title="The dashboard could not load its data">
            <p className="error">{gate.detail}</p>
          </Card>
        )}
        {gate.state === "ok" && page === "frequencies" && <FrequenciesPage />}
        {gate.state === "ok" && page === "response" && <ResponsePage />}
        {gate.state === "ok" && page === "subsets" && <SubsetsPage />}
      </main>
    </div>
  );
}
