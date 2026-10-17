import { useState } from 'react';
import { Layers3, RefreshCw, ArrowUpRight } from 'lucide-react';
import type { CandidateMap } from '../../catalog/entity/catalog';
import { useSpatial } from '../controller/useSpatial';
import { displayPoint } from '../service/projectionService';

export function SpatialComparison({
  map,
  authenticated,
}: {
  map: CandidateMap;
  authenticated: boolean;
}) {
  const spatial = useSpatial();
  const [osm, setOsm] = useState(true),
    [reference, setReference] = useState(true),
    [selected, setSelected] = useState('');
  const data = spatial.data,
    building = data?.buildings.find((b) => b.id === selected);
  const { widthM, depthM, origin } = map.snapshot;
  return (
    <section className="spatial-comparison">
      <div className="spatial-heading">
        <div>
          <span className="eyebrow">PUBLIC GEOMETRY CHECK</span>
          <h2>서로 다른 건물 자료를 겹쳐 보기</h2>
        </div>
        <button
          className="outline-button"
          disabled={!authenticated || spatial.busy}
          onClick={() => void spatial.load()}
        >
          {data ? <RefreshCw size={15} /> : <Layers3 size={15} />}
          {spatial.busy ? '공간자료 조회 중' : data ? '자료 다시 조회' : '저장된 수치지형도 보기'}
        </button>
      </div>
      <p>
        2025년 수치지형도의 건물 경계·지상 층수와 초기 OSM 경계를 대조합니다. 보관한 자료를
        불러오며, 외부 API를 호출하지 않습니다. 새 플레이에는 현재 제공 중인 최신 지도를 자동
        적용합니다.
      </p>
      {!authenticated && <p className="micro-note">로그인 후 조회할 수 있습니다.</p>}
      {spatial.error && (
        <p role="alert" className="form-error">
          {spatial.error}
        </p>
      )}
      {data && (
        <>
          <div className="spatial-controls">
            <label>
              <input type="checkbox" checked={osm} onChange={(e) => setOsm(e.target.checked)} />
              OSM {map.buildings.length}개
            </label>
            <label>
              <input
                type="checkbox"
                checked={reference}
                onChange={(e) => setReference(e.target.checked)}
              />
              수치지형도 {data.buildings.length}도형
            </label>
            <span>
              지상 층수 있음 {data.buildings.filter((b) => b.aboveGroundFloors !== null).length}개
            </span>
          </div>
          <svg
            className="spatial-map"
            viewBox={`${-widthM / 2} ${-depthM / 2} ${widthM} ${depthM}`}
            role="img"
            aria-label="성수 지역 OSM과 수치지형도 건물 경계 대조 지도"
          >
            {osm &&
              map.buildings.map((b) => (
                <polygon
                  key={b.id}
                  points={b.coordinates.map(([x, y]) => `${x},${-y}`).join(' ')}
                  className="osm-outline"
                />
              ))}
            {reference &&
              data.buildings.map((b) => (
                <path
                  key={b.id}
                  d={b.polygons
                    .map((p) =>
                      p
                        .map(
                          (r) =>
                            r
                              .map(
                                (xy, i) => `${i ? 'L' : 'M'}${displayPoint(xy, origin).join(',')}`
                              )
                              .join(' ') + ' Z'
                        )
                        .join(' ')
                    )
                    .join(' ')}
                  className={`reference-outline ${selected === b.id ? 'selected' : ''}`}
                  fillRule="evenodd"
                  onClick={() => setSelected(b.id)}
                >
                  <title>
                    {b.name || '이름 미제공'} ·{' '}
                    {b.aboveGroundFloors === null ? '층수 미확인' : `지상 ${b.aboveGroundFloors}층`}
                  </title>
                </path>
              ))}
          </svg>
          <label className="spatial-selector">
            건물 정보 확인
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">경계 또는 목록에서 선택</option>
              {data.buildings.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name || b.id} ·{' '}
                  {b.aboveGroundFloors === null ? '층수 미확인' : `${b.aboveGroundFloors}층`}
                </option>
              ))}
            </select>
          </label>
          {building && (
            <p>
              <b>{building.name || '이름 미제공'}</b> ·{' '}
              {building.aboveGroundFloors === null
                ? '지상 층수 미확인'
                : `지상 ${building.aboveGroundFloors}층`}{' '}
              · 실측 높이·지표고 미제공
            </p>
          )}
          <p className="micro-note">
            OSM은 중심점, 수치지형도는 영역 교차 기준으로 선택했습니다. 도엽 경계의 분할 도형을
            합치지 않았으므로 건수 차이는 누락 건물 수가 아닙니다. 2025년 자료와 2024년 강우 당시
            형상의 일치 여부는 확인되지 않았습니다. 층수를 높이나 지표고로 환산하지 않습니다.
          </p>
          <p className="footnote">
            출처: {data.provider} · {data.layer} · 표시 좌표계 {data.requestedCrs}
            <br />
            제작 {data.dataYear}년 · 취득 {new Date(data.retrievedAt).toLocaleString('ko-KR')} ·
            원본 보관
            <br />
            고정 자료 버전 <code title={data.snapshotHash}>{data.snapshotHash.slice(0, 12)}</code>
            {' · '}공공누리 제1유형 · 수문 모델 입력과 별도
            <br />
            <a href={data.sourceUrl} target="_blank" rel="noreferrer">
              제공 항목과 이용 안내 <ArrowUpRight size={12} />
            </a>
          </p>
        </>
      )}
    </section>
  );
}
