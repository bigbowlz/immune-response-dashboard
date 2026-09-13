import type { ReactNode } from "react";

interface Props { title?: string; subtitle?: string; actions?: ReactNode; nested?: boolean; children: ReactNode }

export function Card({ title, subtitle, actions, nested, children }: Props) {
  return (
    <section className={nested ? "card card--nested" : "card"}>
      {(title || actions) && (
        <div className="card__head">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
