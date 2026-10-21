import districtMap from '../../district/repository/districtMap.json';
import type { CompetitionCatalog } from '../dto/competitionDto';

export function CompetitionDistrictPicker({
  districts,
  selected,
  onChange,
  disabled,
}: {
  districts: CompetitionCatalog['districts'];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled: boolean;
}) {
  const allowed = new Set(districts.map((d) => d.id));
  function toggle(id: string) {
    if (!disabled && allowed.has(id))
      onChange(
        selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id]
      );
  }
  return (
    <div className="contest-district-picker">
      <div className="contest-selection-toolbar">
        <span aria-live="polite">
          {selected.length === districts.length ? '서울 전체' : `${selected.length}개 구 선택`}
        </span>
        <div>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange(districts.map((d) => d.id))}
          >
            서울 전체 선택
          </button>
          <button type="button" disabled={disabled} onClick={() => onChange([])}>
            모두 해제
          </button>
        </div>
      </div>
      <p className="contest-selection-hint">지도에서 대회에 포함할 구를 선택하세요.</p>
      <svg
        viewBox={districtMap.viewBox}
        className="contest-district-map"
        role="group"
        aria-label="대회 지역 선택 지도"
      >
        {districtMap.districts.map((district) => {
          const active = selected.includes(district.id);
          const unavailable = disabled || !allowed.has(district.id);
          return (
            <g
              key={district.id}
              role="button"
              aria-label={district.name}
              aria-pressed={active}
              aria-disabled={unavailable}
              tabIndex={unavailable ? -1 : 0}
              className={`contest-district${active ? ' is-selected' : ''}`}
              onClick={() => toggle(district.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  toggle(district.id);
                }
              }}
            >
              <path d={district.path} fillRule="evenodd" />
              <text
                x={district.center[0]}
                y={district.center[1]}
                dominantBaseline="middle"
                textAnchor="middle"
              >
                {district.name}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="contest-map-caption">
        <span>
          <i />
          선택한 지역
        </span>
        <a href={districtMap.sourceUrl} target="_blank" rel="noreferrer">
          서울시 자치구 경계
        </a>
      </div>
    </div>
  );
}
