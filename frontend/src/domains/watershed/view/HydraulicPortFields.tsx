import type { StoragePort } from '../dto/storageDto';
export function HydraulicPortFields({
  label,
  value,
  onChange,
}: {
  label: string;
  value: StoragePort;
  onChange: (value: StoragePort) => void;
}) {
  return (
    <fieldset>
      <legend>{label}</legend>
      {(
        [
          ['crestM', '개구부 하단 기준고 (m)', -1000, 10000],
          ['diameterM', '원형 구경 (m)', 0.001, 100],
          ['dischargeCoefficient', '방류계수', 0.001, 1],
        ] as const
      ).map(([key, text, min, max]) => (
        <label key={key}>
          {text}
          <input
            type="number"
            min={min}
            max={max}
            step="0.001"
            value={Number.isFinite(value[key]) ? value[key] : ''}
            onChange={(e) => onChange({ ...value, [key]: e.target.valueAsNumber })}
          />
        </label>
      ))}
      <label className="watershed-check">
        <input
          type="checkbox"
          checked={value.flapGate}
          onChange={(e) => onChange({ ...value, flapGate: e.target.checked })}
        />
        역류 방지 플랩
      </label>
    </fieldset>
  );
}
