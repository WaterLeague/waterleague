import { Landmark, Waves } from 'lucide-react';
import { useState } from 'react';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { traceColor } from '../../floodtrace/service/floodTraceService';
import { infrastructureNames } from '../../infrastructure/service/infrastructureService';
import { HomePreview } from './HomePreview';

export function HomeMapGuide() {
  const [kind, setKind] = useState<InfrastructureAsset['kind']>('STORM_PUMP');
  return (
    <section
      className="home-features home-map-guide"
      id="home-map"
      aria-labelledby="home-map-title"
    >
      <div className="home-section-heading">
        <span className="home-eyebrow">지도 읽기</span>
        <h2 id="home-map-title">침수 기록과 실제 시설도 함께</h2>
        <p>시설을 놓기 전, 그 지역에 어떤 기록과 시설이 있는지 살펴보세요.</p>
      </div>
      <div className="home-feature-grid home-map-grid">
        <article>
          <HomePreview map="flood" label="과거 침수 기록" />
          <span className="home-map-legend" style={{ color: traceColor }}>
            <Waves size={22} aria-hidden="true" /> 보라색 · 과거 침수 기록
          </span>
          <h3>물이 닿았던 지역 살펴보기</h3>
          <p>
            서울시 침수흔적도를 겹쳐 2010·2011·2022년 호우 때 침수가 기록된 범위를 확인해요. 주간
            모드는 지도 도구에서 과거 사건을 고르고, 재해 모드는 선택한 호우의 기록을 보여줘요.
          </p>
          <dl className="home-map-facts">
            <div>
              <dt>과거의 기록</dt>
              <dd>사건 전체의 침수 범위이며 재생 시각에 따라 깊이가 변하는 자료는 아니에요.</dd>
            </div>
            <div>
              <dt>현재 계산 범위</dt>
              <dd>
                시설별 빗물 효과를 계산해요. 서울 전역의 실시간 침수 수심·유속은 제공하지 않아요.
              </dd>
            </div>
          </dl>
        </article>
        <article>
          <HomePreview
            map="infrastructure"
            infrastructure={kind}
            label={infrastructureNames[kind]}
          />
          <span className="home-map-legend is-infrastructure">
            <Landmark size={22} aria-hidden="true" /> 주황색 · 공개 기존 시설
          </span>
          <h3>서울에 이미 설치된 시설</h3>
          <p>
            공개자료에 등록된 시설을 게임에서 직접 놓은 시설과 구분해 표시해요. 지도에서 누르거나
            시설명으로 검색하면 위치·출처와 확보된 제원·설치 이력을 살펴볼 수 있어요.
          </p>
          <div className="home-map-kinds" role="group" aria-label="소개할 공개 기존 시설 선택">
            {Object.entries(infrastructureNames).map(([value, name]) => (
              <button
                type="button"
                key={value}
                aria-pressed={kind === value}
                onClick={() => setKind(value as InfrastructureAsset['kind'])}
              >
                {name}
              </button>
            ))}
          </div>
          <p className="home-map-note">
            자료의 기준 시점을 함께 확인하세요. 위치 정보만으로 현재 가동 상태나 과거 호우 당시의
            운영 여부가 확인되는 것은 아니에요.
          </p>
        </article>
      </div>
      <p className="home-caption">
        3D는 지도 표시 방식과 시설 형태를 설명하는 모형이며, 실제 장소의 침수 범위나 시설 치수를
        뜻하지 않아요.
      </p>
    </section>
  );
}
