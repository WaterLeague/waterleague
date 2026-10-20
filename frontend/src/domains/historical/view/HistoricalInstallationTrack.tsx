import { facilityIcons } from '../../facility/view/facilityIcons';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import type { HistoricalDraft } from '../entity/historical';
import { facilities } from '../../game/service/gameService';
import { installationTimelineGroups } from '../service/historicalTimelineService';

const clock = new Intl.DateTimeFormat('ko-KR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
  timeZone: 'Asia/Seoul',
});
export function HistoricalInstallationTrack({
  drafts,
  start,
  duration,
  elapsed,
  onSelect,
  children,
}: {
  drafts: HistoricalDraft[];
  start?: string;
  duration: number;
  elapsed: number;
  onSelect: (draft: HistoricalDraft, seconds: number) => void;
  children: ReactNode;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);
  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const groups = useMemo(
    () => installationTimelineGroups(drafts, start, duration, width),
    [drafts, start, duration, width]
  );
  const label = (draft: HistoricalDraft) =>
    `${clock.format(new Date(draft.marker.installedAt))} ${facilities[draft.facilityType].name} · ${draft.site.name}`;
  return (
    <div ref={track} className="historical-time-track" data-has-markers={groups.length > 0}>
      {children}
      <div className="historical-track-events" aria-label="타임라인 설치 기록">
        {groups.map((group) => {
          const event = group.events[0];
          const Icon = facilityIcons[event.draft.facilityType];
          const style = { left: `calc(12px + (100% - 24px) * ${group.position})` };
          const reached = event.seconds <= elapsed;
          return group.events.length === 1 ? (
            <button
              key={group.id}
              className="historical-time-pin"
              style={style}
              data-reached={reached}
              aria-label={label(event.draft)}
              title={label(event.draft)}
              onClick={() => onSelect(event.draft, event.seconds)}
            >
              <Icon size={14} aria-hidden="true" />
            </button>
          ) : (
            <details
              key={group.id}
              className="historical-time-cluster"
              style={style}
              data-reached={reached}
            >
              <summary
                aria-label={`${clock.format(new Date(event.draft.marker.installedAt))} 부근 설치 ${group.events.length}개`}
                title={`설치 ${group.events.length}개`}
              >
                <span>{group.events.length}</span>
              </summary>
              <div
                className="historical-time-choices"
                style={{
                  left: group.position > 0.5 ? 'auto' : 0,
                  right: group.position > 0.5 ? 0 : 'auto',
                }}
              >
                {group.events.map((entry) => {
                  const EntryIcon = facilityIcons[entry.draft.facilityType];
                  return (
                    <button
                      key={entry.draft.marker.id}
                      onClick={(event) => {
                        event.currentTarget.closest('details')?.removeAttribute('open');
                        onSelect(entry.draft, entry.seconds);
                      }}
                    >
                      <EntryIcon size={14} aria-hidden="true" />
                      <span>{label(entry.draft)}</span>
                    </button>
                  );
                })}
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
}
