import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
export function GameSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const selected = Math.max(
    0,
    options.findIndex((o) => o.value === value)
  );
  const [active, setActive] = useState(selected);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [open]);
  useEffect(() => {
    if (open)
      root.current
        ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
        ?.scrollIntoView({ block: 'nearest' });
  }, [active, open]);
  const choose = (index: number) => {
    onChange(options[index].value);
    setOpen(false);
    trigger.current?.focus();
  };
  return (
    <div
      className="game-select"
      ref={root}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={id}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        onClick={() => {
          setActive(selected);
          setOpen((v) => !v);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            setOpen(false);
            e.stopPropagation();
            return;
          }
          if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
            e.preventDefault();
            setOpen(true);
            setActive((i) =>
              e.key === 'Home'
                ? 0
                : e.key === 'End'
                  ? options.length - 1
                  : Math.max(
                      0,
                      Math.min(
                        options.length - 1,
                        (open ? i : selected) + (e.key === 'ArrowDown' ? 1 : -1)
                      )
                    )
            );
          } else if (open && ['Enter', ' '].includes(e.key)) {
            e.preventDefault();
            choose(active);
          } else if (e.key.length === 1 && e.key !== ' ') {
            const i = options.findIndex((o) => o.label.startsWith(e.key));
            if (i >= 0) {
              setOpen(true);
              setActive(i);
            }
          }
        }}
      >
        <span>{options.find((o) => o.value === value)?.label ?? label}</span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div id={id} role="listbox" aria-label={label} className="game-select-options">
          {options.map((o, i) => (
            <div
              key={o.value}
              id={`${id}-${i}`}
              role="option"
              aria-selected={o.value === value}
              data-index={i}
              data-active={i === active}
              onMouseEnter={() => setActive(i)}
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => choose(i)}
            >
              <span>{o.label}</span>
              {o.value === value && <Check size={14} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
