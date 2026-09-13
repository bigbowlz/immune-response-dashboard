import type { ReactNode } from "react";

export function Chip({ tone = "neutral", children }: { tone?: "green" | "neutral" | "red"; children: ReactNode }) {
  return <span className={`chip chip--${tone}`}>{children}</span>;
}
