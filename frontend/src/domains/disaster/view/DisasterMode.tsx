import { useEffect, useState } from 'react';
import { ArrowUpRight, CloudRain } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { DisasterCatalog } from '../entity/disaster';
import { loadDisasters } from '../repository/disasterRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
import { CityExplorer } from '../../city/view/CityExplorer';
import './disaster.css';
export function DisasterMode(props: {
  account: Account | null;
  onLogin: () => void;
  onAccount: (a: Account) => void;
}) {
  const [catalog, setCatalog] = useState<DisasterCatalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    loadDisasters()
      .then((v) => {
        if (active) setCatalog(v);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  if (selected)
    return (
      <CityExplorer
        {...props}
        mode="historical"
        eventId={selected}
        onExit={() => setSelected(null)}
      />
    );
  return (
    <main className="disaster-lobby">
      <header>
        <span className="eyebrow">DISASTER ARCHIVE / SEOUL</span>
        <h1>그날의 비, 다시 설계하다.</h1>
        <p>
          실제 관측이 남아 있는 재난을 선택하세요. 서울 25개 구에서 당시의 비를 재생하며 시설을
          배치합니다.
        </p>
      </header>
      {error ? (
        <div role="alert">
          {error}
          <button className="outline-button" onClick={() => setAttempt((v) => v + 1)}>
            다시 불러오기
          </button>
        </div>
      ) : !catalog ? (
        <p role="status">재난 기록을 불러오는 중입니다.</p>
      ) : (
        <div className="disaster-cards">
          {catalog.events.map((event, i) => (
            <article key={event.id} className={`disaster-card disaster-card-${i}`}>
              <div className="disaster-card-art" aria-hidden="true">
                <CloudRain size={72} strokeWidth={1} />
                <span>{event.eventDate.slice(0, 4)}</span>
              </div>
              <div className="disaster-card-copy">
                <span>집중호우 · 서울 {event.regions.length}개 구</span>
                <h2>{event.eventDate.replaceAll('-', '. ')} 집중호우</h2>
                <p>{event.summary}</p>
                <small>공개 관측 구간 재생 · 기본 1배속</small>
                <button
                  onClick={() => setSelected(event.id)}
                  aria-label={`${event.eventDate} 집중호우 시작`}
                >
                  이 재난으로 시작 <ArrowUpRight size={18} />
                </button>
                <a href={event.evidenceUrl} target="_blank" rel="noreferrer">
                  {event.evidenceTitle} ↗
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="disaster-lobby-note">
        확보된 서울 관측자료가 있는 사건만 제공합니다. 당시 강우를 현재 공개 지형에 적용하는
        실험이며, 실제 피해를 복원한 지도는 아닙니다.
      </p>
    </main>
  );
}
