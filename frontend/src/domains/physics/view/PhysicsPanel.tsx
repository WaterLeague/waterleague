import { Droplets } from 'lucide-react';
import { usePhysics } from '../controller/usePhysics';
import './physics.css';
const amount = (n: number | null, scale = 1) =>
  n === null
    ? '—'
    : new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 }).format(Math.max(0, n * scale));
const at = (time: string) =>
  new Date(time).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Seoul',
  });
export function PhysicsPanel({ installationId }: { installationId: string }) {
  const { value, error } = usePhysics(installationId);
  const result = value?.result;
  return (
    <section className="shared-physics" aria-label="시설 물리 계산">
      <h3>
        <Droplets size={17} /> 시설의 물 흐름
      </h3>
      <p className="physics-status" role="status">
        {error || value?.message || '계산 상태 확인 중'}
      </p>
      {result && (
        <>
          <small>
            {at(result.simulatedThrough)}까지 계산 · {result.stationName} 관측 강우
          </small>
          <dl>
            <div>
              <dt>누적 침투</dt>
              <dd>
                {amount(result.infiltrationM3)} <small>m³</small>
              </dd>
            </div>
            <div>
              <dt>누적 유출·배수</dt>
              <dd>
                {amount(result.runoffM3)} <small>m³</small>
              </dd>
            </div>
            <div>
              <dt>현재 수분·저류</dt>
              <dd>
                {amount(result.storageM3)} <small>m³</small>
              </dd>
            </div>
            <div>
              <dt>시설 표면 수심</dt>
              <dd>
                {amount(result.surfaceDepthMm)} <small>mm</small>
              </dd>
            </div>
            {result.soilMoisture !== null && (
              <div>
                <dt>토양 수분율</dt>
                <dd>
                  {amount(result.soilMoisture, 100)} <small>%</small>
                </dd>
              </div>
            )}
          </dl>
          <details>
            <summary>계산 조건</summary>
            <p>
              EPA SWMM {result.engineVersion} · {at(result.simulationStart)} 이후 연속 계산
            </p>
            <p>
              물수지 오차 {amount(Math.abs(result.runoffContinuityPercent))}% · 누적 강우 체적{' '}
              {amount(result.precipitationM3)} m³
            </p>
            <p>
              공개 관측 강우에 따른 모델 결과입니다. 시설 재료·초기 수분·토양·경사는 미확인 설계
              조건입니다.
            </p>
            <p>
              {result.evaporationMethod === 'ASSUMED_MODEL_CONSTANT'
                ? '증발산 기상 입력 연결 전으로 0 조건 적용 중입니다.'
                : '기상자료에서 계산한 잠재 증발률 적용 중입니다.'}{' '}
              실제 침수 깊이나 현장 계측값은 아닙니다.
            </p>
          </details>
        </>
      )}
      {!result && <small>유효한 관측과 계산 결과가 확보되면 표시됩니다.</small>}
    </section>
  );
}
