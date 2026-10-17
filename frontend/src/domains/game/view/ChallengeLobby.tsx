import { ArrowRight, ArrowUpRight, CloudRain, MapPin, Trophy } from 'lucide-react';
import type { Lab, RainfallCatalog } from '../entity/game';
import type { CandidateMap } from '../../catalog/entity/catalog';
import { MapViewport } from '../../catalog/view/MapViewport';
import type { League } from '../../league/entity/league';
import { facilities, format, won } from '../service/gameService';
import { sameMapModels, rainfallLabel, rainfallNote } from '../service/modelFamilyService';
import { rainDate } from './RainfallSelector';

export function ChallengeLobby({
  lab,
  catalog,
  map,
  busy,
  hasDesign,
  league,
  onFreePlay,
  onSelect,
  onPlay,
  onCompetition,
  onEvidence,
}: {
  lab: Lab;
  catalog: RainfallCatalog | null;
  map: CandidateMap | null;
  busy: boolean;
  hasDesign: boolean;
  league: League | null;
  onFreePlay: () => void;
  onSelect: (hash: string) => void;
  onPlay: () => void;
  onCompetition: () => void;
  onEvidence: () => void;
}) {
  const families = [
    ...new Map((catalog?.models ?? []).map((m) => [m.mapId ?? 'legacy', m])).values(),
  ];
  const current = catalog?.models.find((m) => m.modelHash === lab.modelHash);
  return (
    <main className="challenge-lobby">
      <div className="challenge-heading">
        <span>WATER LEAGUE / SEOUL</span>
        <span>
          <MapPin size={14} /> {current?.mapTitle ?? '성수 · 연무장길'}
        </span>
      </div>
      <section className="challenge-hero" aria-label="지역 빗물 도전">
        <div className="challenge-copy">
          <span className="challenge-kicker">
            {league ? `기관 리그 · ${league.title}` : '도시를 바꾸는 한 수'}
          </span>
          <h1>
            같은 비.
            <br />
            다른 <em>선택.</em>
          </h1>
          <p>
            지붕 위에, 길 옆에.
            <br />
            빗물이 머물 자리를 만들고
            <br />
            당신의 설계로 기록에 도전하세요.
          </p>
          <dl className="challenge-rules">
            <div>
              <dt>예산 상한</dt>
              <dd>{won(league?.rules.budget ?? lab.model.budget)}</dd>
            </div>
            <div>
              <dt>시설</dt>
              <dd>
                {league
                  ? league.rules.allowedTypes.map((type) => facilities[type].name).join(' · ')
                  : '빗물정원 · 투수포장 · 녹화지붕'}
              </dd>
            </div>
            <div>
              <dt>목표</dt>
              <dd>같은 강우에서 유출·잔여저류 줄이기</dd>
            </div>
          </dl>
          <button className="challenge-start" disabled={busy} onClick={onPlay}>
            {busy
              ? '도전 조건 불러오는 중'
              : league
                ? '리그 플레이 이어가기'
                : hasDesign
                  ? '이어서 플레이'
                  : '플레이 시작'}{' '}
            <ArrowRight size={21} />
          </button>
          <small>배치는 로그인 없이 체험 · 저장과 계산은 로그인 후</small>
        </div>
        <div className="challenge-city">
          {map ? (
            <MapViewport
              map={map}
              cells={[]}
              placements={[]}
              selectedCell={null}
              onSelect={() => {}}
            />
          ) : (
            <p role="status">선택한 지역의 건물을 불러오는 중</p>
          )}
          <div className="challenge-city-caption">
            <span>{current?.mapTitle ?? '성수'}</span>
            <b>실제 동네에서 시작하는 전략</b>
            <small>{map?.snapshot.title} · 지형 평탄화 · 높이 가정</small>
          </div>
        </div>
      </section>
      <section className="challenge-events" aria-labelledby="challenge-events-title">
        <div className="challenge-section-title">
          <h2 id="challenge-events-title">어떤 비에 도전할까요?</h2>
          <span>{rainfallNote(lab.model.regionalRainfallUse)}</span>
        </div>
        <label className="challenge-map-choice">
          지도 버전
          <select
            aria-label="지도 버전 선택"
            disabled={busy || !!league}
            value={current?.mapId ?? 'legacy'}
            onChange={(e) => {
              const target =
                catalog?.models.find(
                  (m) =>
                    (m.mapId ?? 'legacy') === e.target.value &&
                    m.rainfall.sourceHash === lab.model.rainfall.sourceHash
                ) ?? families.find((m) => (m.mapId ?? 'legacy') === e.target.value);
              if (target) onSelect(target.modelHash);
            }}
          >
            {families.map((m) => (
              <option key={m.mapId ?? 'legacy'} value={m.mapId ?? 'legacy'}>
                {m.mapTitle ?? '기존 지도'}
              </option>
            ))}
          </select>
          <small>지도 변경 시 새 배치로 시작 · 기존 저장 기록 유지</small>
        </label>
        {league && (
          <p className="challenge-copy-note">
            리그의 강우·예산·시설은 고정됩니다.{' '}
            <button className="text-button" disabled={busy} onClick={onFreePlay}>
              일반 도전으로 전환 <ArrowRight size={14} />
            </button>
          </p>
        )}
        <div
          className={`challenge-event-list${lab.model.regionalRainfallUse ? ' regional-events' : ''}`}
        >
          {sameMapModels(catalog, lab.modelHash).map((item, index) => (
            <button
              key={item.modelHash}
              aria-pressed={lab.modelHash === item.modelHash}
              disabled={busy || !!league}
              onClick={() => onSelect(item.modelHash)}
            >
              <span className="event-index">
                0{index + 1} <CloudRain size={19} />
              </span>
              <b>{rainDate(item.rainfall.start)}</b>
              <span>
                {rainfallLabel(item.regionalRainfallUse)} · {item.rainfall.stationName}
                {item.rainfall.stationDistanceKm != null &&
                  ` · ${item.rainfall.stationDistanceKm} km`}
              </span>
              <strong>
                {format.format(item.rainfall.totalDepthMm)}
                <small>mm</small>
              </strong>
              <span className="event-state">
                {lab.modelHash === item.modelHash ? '선택한 도전' : '이 강우 선택'}
                <ArrowUpRight size={16} />
              </span>
            </button>
          ))}
        </div>
        {hasDesign && !league && (
          <p className="challenge-copy-note">
            호환되는 강우로 바꾸면 현재 배치를 복사합니다. 기록은 각 조건에 따로 남습니다.
          </p>
        )}
      </section>
      <footer className="challenge-footer">
        <p>
          <b>탐색 모델</b> 현장 보정 전입니다. 결과는 실제 침수나 공사 효과를 예측하지 않습니다.{' '}
          <button onClick={onEvidence}>
            자료·가정 확인 <ArrowUpRight size={13} />
          </button>
        </p>
        <button className="challenge-competition" onClick={onCompetition}>
          <Trophy size={18} /> 기록 경쟁·기관 리그 <ArrowRight size={16} />
        </button>
      </footer>
    </main>
  );
}
