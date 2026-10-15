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
    [vworld, setVworld] = useState(true),
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
          {spatial.busy ? '공간자료 조회 중' : data ? '자료 다시 조회' : '브이월드 건물 조회'}
        </button>
      </div>
      <p>
        도로명주소 건물 경계·지상 층수와 현재 게임의 OSM 경계를 대조합니다. 이 조회 자료는
        시뮬레이션 입력에 포함되지 않습니다.
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
                checked={vworld}
                onChange={(e) => setVworld(e.target.checked)}
              />
              브이월드 {data.buildings.length}개
            </label>
            <span>
              지상 층수 있음 {data.buildings.filter((b) => b.aboveGroundFloors !== null).length}개
            </span>
          </div>
          <svg
            className="spatial-map"
            viewBox={`${-widthM / 2} ${-depthM / 2} ${widthM} ${depthM}`}
            role="img"
            aria-label="성수 지역 OSM과 브이월드 건물 경계 대조 지도"
          >
            {osm &&
              map.buildings.map((b) => (
                <polygon
                  key={b.id}
                  points={b.coordinates.map(([x, y]) => `${x},${-y}`).join(' ')}
                  className="osm-outline"
                />
              ))}
            {vworld &&
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
                  className={`vworld-outline ${selected === b.id ? 'selected' : ''}`}
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
            OSM은 중심점, 브이월드는 영역 교차 기준 조회입니다. 건수 차이는 누락 수가 아닙니다. 현재
            제공 자료와 2024년 강우 당시 형상의 일치 여부는 확인되지 않았습니다. 층수를 높이나
            지표고로 환산하지 않습니다.
          </p>
          <p className="footnote">
            출처: {data.provider} · {data.layer} · 요청 좌표계 {data.requestedCrs}
            <br />
            조회 {new Date(data.retrievedAt).toLocaleString('ko-KR')} · 원본 서버 저장·연구 내보내기
            없음 · 화면 이탈 시 조회 내용 해제
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
