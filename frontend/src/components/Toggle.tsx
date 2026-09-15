interface Props {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/** A labelled switch: a native checkbox with the switch role, drawn as a track and thumb. */
export function Toggle({ label, checked, onChange, disabled }: Props) {
  return (
    <label className="toggle">
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" aria-hidden="true"><span className="toggle__thumb" /></span>
      <span className="toggle__label">{label}</span>
    </label>
  );
}
