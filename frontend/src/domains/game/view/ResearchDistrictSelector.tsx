import { useDistricts } from '../../district/controller/useDistricts';
import type { Lab, RainfallCatalog } from '../entity/game';

export function ResearchDistrictSelector({
  lab,
  catalog,
  disabled,
  onSelect,
}: {
  lab: Lab;
  catalog: RainfallCatalog | null;
  disabled: boolean;
  onSelect: (hash: string) => void;
}) {
  const { districts, error } = useDistricts();
  // 성수 연구 구역은 카탈로그의 최신 수치지형도 모델, 나머지는 구별 기본 모델 사용.
  const seongdong = '2419953';
  const selected = districts.find((d) => d.mapId === lab.model.mapId)?.id ?? seongdong;
  return (
    <div className="research-district">
      <label>
        연구 지역
        <select
          aria-label="연구 지역 선택"
          value={selected}
          disabled={disabled || !catalog || !districts.length}
          onChange={(e) => {
            const region = districts.find((d) => d.id === e.target.value);
            if (region && catalog)
              onSelect(region.id === seongdong ? catalog.defaultModelHash : region.modelHash);
          }}
        >
          {!districts.length && <option value={selected}>지역 목록 불러오는 중</option>}
          {districts.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      <small>{error || '지역별 최신 지도 자동 적용'}</small>
    </div>
  );
}
