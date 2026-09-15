import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export interface SelectOption { value: string; label: string }

interface Props {
  id: string;
  label: string;
  value: string;
  options: SelectOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}

/** A listbox-style dropdown whose menu opens below the control, so the current value stays readable. */
export function Select({ id, label, value, options, disabled, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false); // keeps the menu mounted while it animates shut
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) hide(); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const show = () => {
    setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    setClosing(false);
    setOpen(true);
  };
  const hide = () => {
    setOpen(false);
    setClosing(true);
  };
  const choose = (index: number) => {
    const option = options[index];
    if (option) onChange(option.value);
    hide();
    root.current?.querySelector("button")?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) show(); else setActive((i) => Math.min(options.length - 1, i + 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!open) show(); else setActive((i) => Math.max(0, i - 1));
        break;
      case "Home": if (open) { e.preventDefault(); setActive(0); } break;
      case "End": if (open) { e.preventDefault(); setActive(options.length - 1); } break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (open) choose(active); else show();
        break;
      case "Escape": if (open) { e.preventDefault(); hide(); } break;
      case "Tab": if (open) hide(); break;
    }
  };

  return (
    <div className="select" ref={root}>
      <button
        type="button"
        id={id}
        className="select__button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={() => (open ? hide() : show())}
        onKeyDown={onKeyDown}
      >
        <span className="select__value">{current?.label ?? ""}</span>
        <span className="select__chevron" aria-hidden="true" />
      </button>
      {(open || closing) && (
        <ul
          className={`select__menu${open ? "" : " select__menu--closing"}`}
          role="listbox"
          id={menuId}
          aria-label={label}
          aria-hidden={!open}
          onAnimationEnd={() => { if (!open) setClosing(false); }}
        >
          {options.map((o, index) => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              data-index={index}
              className={`select__option${index === active ? " select__option--active" : ""}`}
              onMouseEnter={() => setActive(index)}
              onMouseDown={(e) => { e.preventDefault(); choose(index); }}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
