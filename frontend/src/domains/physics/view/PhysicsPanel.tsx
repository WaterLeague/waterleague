import { InitializationEvidence } from './InitializationEvidence';
import { FacilityProfileEvidence } from '../../facility/view/FacilityProfileEvidence';
import { Droplets } from 'lucide-react';
import { usePhysics } from '../controller/usePhysics';
import './physics.css';
import { RunoffComparison } from './RunoffComparison';
import { LifeCycleCostEvidence } from '../../cost/view/LifeCycleCostEvidence';
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
        {error ||
          (value?.status === 'READY' ? '시설 내부 계산 결과' : value?.message) ||
          '계산 상태 확인 중'}
      </p>
      {result && (
        <>
          <small>{at(result.simulatedThrough)}까지 계산</small>
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
          {result.runoffComparison && (
            <RunoffComparison value={result.runoffComparison} contract={result.designContract} />
          )}
          <details>
            <summary>계산 조건</summary>
            {result.lifeCycleCost && <LifeCycleCostEvidence value={result.lifeCycleCost} />}
            {result.initialization && <InitializationEvidence value={result.initialization} />}
            {result.facilityDesign && <FacilityProfileEvidence {...result.facilityDesign} />}
            <p>
              EPA SWMM {result.engineVersion} · {at(result.simulationStart)} 이후 연속 계산
            </p>
            <p>
              물수지 오차 {amount(Math.abs(result.runoffContinuityPercent))}% · 누적 강우 체적{' '}
              {amount(result.precipitationM3)} m³
            </p>
            <p>
              {result.inflowPolicy === 'DIRECT_RAINFALL_ONLY'
                ? '시설 자체 강우만 처리하며, 배수 연결이 확인되지 않은 주변 표면의 유출은 가산하지 않습니다.'
                : '기존 설치 당시의 유입 조건을 보존한 계산입니다.'}
            </p>
            <p>
              설치 당시 입력과 실제 기상자료로 계산한 결과입니다. 후보별 공간자료와 문헌 추정,
              미확보 설계 조건은 저장된 계산 기록에서 구분합니다.
            </p>
            <p>
              {result.evaporationMethod === 'ASSUMED_MODEL_CONSTANT'
                ? '증발산 기상 입력 연결 전으로 0 조건 적용 중입니다.'
                : '서울 관측소의 일사·기온·습도·풍속·기압으로 계산한 기준 증발산을 적용합니다. 직전 완료 시간의 값을 다음 시간에 유지하며, 시설별 보정 전입니다.'}{' '}
              실제 침수 깊이나 현장 계측값은 아닙니다.
            </p>
          </details>
        </>
      )}
      {!result && <small>유효한 관측과 계산 결과가 확보되면 표시됩니다.</small>}
    </section>
  );
}
