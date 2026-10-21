import { facilities } from '../../game/service/gameService';
import type { CompetitionCatalog } from '../dto/competitionDto';
import type { z } from 'zod';
import type { installationDto } from '../dto/competitionDto';
export const competitionTime = (value: string, seconds = false) =>
  new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(seconds ? { second: '2-digit' as const } : {}),
  });
export const phaseNames = {
  UPCOMING: '개최 예정',
  OPEN: '진행 중',
  ENDED: '종료',
  CANCELLED: '취소',
};
export const resultNames = {
  UPCOMING: '개최 예정',
  IN_PROGRESS: '진행 중 순위',
  PROVISIONAL: '최종 계산 중',
  WITHHELD: '비교 보류',
  EMPTY: '제출 기록 없음',
  FINAL: '최종 결과',
  CANCELLED: '취소된 대회',
};
export function Pagination({
  page,
  hasMore,
  onPage,
}: {
  page: number;
  hasMore: boolean;
  onPage: (page: number) => void;
}) {
  return (
    <div className="contest-pagination">
      <button className="outline-button" disabled={page === 0} onClick={() => onPage(page - 1)}>
        이전
      </button>
      <span>{page + 1} 페이지</span>
      <button className="outline-button" disabled={!hasMore} onClick={() => onPage(page + 1)}>
        다음
      </button>
    </div>
  );
}
export function InstallationTimes({
  items,
  catalog,
}: {
  items: z.infer<typeof installationDto>[];
  catalog: CompetitionCatalog;
}) {
  if (!items.length) return <span>—</span>;
  return (
    <details className="contest-installations">
      <summary>시설 {items.length}개 · 설치 시각</summary>
      <ul>
        {items.map((i) => (
          <li key={i.id}>
            <strong>
              {facilities[i.facilityType].name} · {i.areaM2.toLocaleString()} m²
            </strong>
            <span>
              {catalog.districts.find((d) => d.id === i.districtId)?.name} ·{' '}
              {competitionTime(i.installedAt, true)}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
