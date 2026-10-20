export function CisternSizeControl({
  area,
  maxArea,
  onArea,
}: {
  area: number;
  maxArea: number;
  onArea: (value: string) => void;
}) {
  const capacity = (value: number) =>
    (value * 0.01).toLocaleString('ko-KR', { maximumFractionDigits: 3 });
  return (
    <div className="cistern-size-control">
      <strong>이용조 크기 · {capacity(area)}㎥</strong>
      <div className="facility-options" aria-label="이용조 크기 선택">
        {[
          ['소형', 0.25],
          ['중형', 0.5],
          ['대형', 1],
        ].map(([label, ratio]) => {
          const value = Math.max(0.01, Math.floor(maxArea * Number(ratio) * 100) / 100);
          return (
            <button
              type="button"
              key={label}
              aria-pressed={area === value}
              className={area === value ? 'selected' : ''}
              onClick={() => onArea(String(value))}
            >
              {label} · {capacity(value)}㎥
            </button>
          );
        })}
      </div>
      <input
        className="area-slider"
        type="range"
        aria-label="이용조 크기 조절"
        min=".01"
        max={maxArea}
        step=".01"
        value={Math.min(maxArea, area || 0.01)}
        onChange={(event) => onArea(event.target.value)}
      />
      <p className="micro-note">
        지붕 집수 {area.toLocaleString('ko-KR')}㎡ · 최대 {capacity(maxArea)}㎥
      </p>
      <p className="micro-note">설치하면 지붕 집수부와 건물 옆 지상 탱크가 함께 배치됩니다.</p>
    </div>
  );
}
