import type { League } from '../entity/league';
import { facilities, won, format } from '../../game/service/gameService';
import { leagueTime, phaseNames } from '../service/leagueService';
export function LeagueRulesPanel({ league: l }: { league: League }) {
  return (
    <div className="league-rules">
      <span className={'state ' + (l.phase === 'OPEN' ? 'done' : '')}>{phaseNames[l.phase]}</span>
      <h2>{l.title}</h2>
      <p className="league-question">{l.question}</p>
      <dl>
        <div>
          <dt>주최</dt>
          <dd>{l.organizationName}</dd>
        </div>
        <div>
          <dt>설치 예산</dt>
          <dd>{won(l.rules.budget)}</dd>
        </div>
        <div>
          <dt>허용 시설</dt>
          <dd>{l.rules.allowedTypes.map((t) => facilities[t].name).join(' · ')}</dd>
        </div>
        <div>
          <dt>제출 한도</dt>
          <dd>회원별 {l.rules.submissionLimit}회 · 최고 점수 반영</dd>
        </div>
        {l.rules.placementLimit != null && l.rules.areaLimitM2 != null && (
          <div>
            <dt>배치 제한</dt>
            <dd>
              최대 {l.rules.placementLimit}개 구역 · 합계 {format.format(l.rules.areaLimitM2)} m²
            </dd>
          </div>
        )}
        <div>
          <dt>접수 기간 · 한국 시간</dt>
          <dd>
            {leagueTime(l.rules.opensAt)} ~ {leagueTime(l.rules.closesAt)}
          </dd>
        </div>
      </dl>
      {l.rules.award && (
        <section className="league-award">
          <h3>상금·심사 안내</h3>
          <strong>
            {l.rules.award.prizeKrw > 0
              ? `총 ${won(l.rules.award.prizeKrw)} · ${l.rules.award.winnerCount}명 예정`
              : '상금 없음'}
          </strong>
          {l.rules.award.notice && <p>{l.rules.award.notice}</p>}
          <small>
            주최 기관의 안내입니다. 수상 선정·지급은 주최 기관이 담당하며 게임 순위와 별도입니다.
            현장 효과 검증을 의미하지 않습니다.
          </small>
        </section>
      )}
      <p className="footnote">
        평가체적 저감률 × 100. 유출·배수·잔여저류·초기저류를 함께 계산하며 음수도 보존합니다. 같은
        서버 점수는 같은 순위입니다.
      </p>
      <details>
        <summary>고정 모델·규칙 확인</summary>
        <dl>
          <div>
            <dt>규칙 SHA-256</dt>
            <dd className="hash-value">{l.rulesHash}</dd>
          </div>
          <div>
            <dt>모델 SHA-256</dt>
            <dd className="hash-value">{l.rules.modelHash}</dd>
          </div>
          <div>
            <dt>엔진 소스</dt>
            <dd className="hash-value">{l.rules.engineRevision}</dd>
          </div>
          <div>
            <dt>생성기 SHA-256</dt>
            <dd className="hash-value">{l.rules.generatorSha256}</dd>
          </div>
        </dl>
        <p>첫 유효 제출의 실행 바이너리 지문과 다른 결과는 같은 리그에 섞지 않습니다.</p>
      </details>
      {l.cancellationReason && <p className="form-error">취소 사유: {l.cancellationReason}</p>}
    </div>
  );
}
