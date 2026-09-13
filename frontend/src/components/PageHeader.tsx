import { useEffect, useRef } from "react";

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [title]);
  return (
    <header className="page-header">
      <h1 ref={heading} tabIndex={-1}>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </header>
  );
}
