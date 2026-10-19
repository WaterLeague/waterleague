import type { HistoricalDraft } from '../entity/historical';

export function installationTimelineGroups(
  drafts: HistoricalDraft[],
  start: string | undefined,
  duration: number,
  width: number
) {
  const origin = Date.parse(start ?? '');
  if (!Number.isFinite(origin) || duration <= 0 || !Number.isFinite(duration)) return [];
  const events = drafts
    .map((draft) => ({ draft, seconds: (Date.parse(draft.marker.installedAt) - origin) / 1000 }))
    .filter(
      (event) => Number.isFinite(event.seconds) && event.seconds >= 0 && event.seconds <= duration
    )
    .sort((a, b) => a.seconds - b.seconds || a.draft.marker.id.localeCompare(b.draft.marker.id));
  const groups: { id: string; position: number; events: typeof events }[] = [];
  const trackWidth = Math.max(1, width - 24);
  for (const event of events) {
    const position = event.seconds / duration;
    const previous = groups.at(-1);
    // 가까운 설치 기록은 묶되 각 기록의 실제 초 단위 시각은 유지한다.
    if (previous && (position - previous.position) * trackWidth < 26) previous.events.push(event);
    else groups.push({ id: event.draft.marker.id, position, events: [event] });
  }
  return groups;
}
