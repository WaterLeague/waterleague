import { Container, House, MapPin, X } from 'lucide-react';
import type { CisternPlanState } from '../controller/useCisternPlans';
import type { SharedSite } from '../entity/installation';
import { CisternReferenceCosts } from '../../watershed/view/CisternReferenceCosts';
import './cistern-plan.css';
export function CisternPlanPanel({
  state: s,
  onClose,
  onChoose,
  onLocate,
  onLogin,
}: {
  state: CisternPlanState;
  onClose: () => void;
  onChoose: (role: 'roof' | 'ground') => void;
  onLocate: (site: SharedSite) => void;
  onLogin: () => void;
}) {
  const capacity = Number(s.area) * Number(s.depth);
  return (
    <aside className="shared-inspector cistern-plan-panel" aria-label="빗물이용조 지도 계획">
      <header className="watershed-heading">
        <div>
          <span>집수 · 저장 위치 계획</span>
          <h2>빗물이용조</h2>
        </div>
        <button aria-label="이용조 계획 닫기" onClick={onClose}>
          <X size={18} />
        </button>
      </header>
      <p>
        빗물을 모을 지붕과 탱크를 둘 땅을 선택하세요. 두 위치의 공개 경계를 함께 확인할 수 있습니다.
      </p>
      <div className="cistern-plan-steps">
        {(['roof', 'ground'] as const).map((role, index) => {
          const site = s[role];
          return (
            <section key={role} className={s.role === role ? 'active' : ''}>
              <button
                onClick={() => onChoose(role)}
                aria-pressed={s.role === role}
                disabled={s.busy}
              >
                {role === 'roof' ? <House size={17} /> : <Container size={17} />}
                <strong>
                  {index + 1}. {role === 'roof' ? '집수할 지붕' : '탱크를 둘 땅'}
                </strong>
              </button>
              {site ? (
                <>
                  <p>{site.name}</p>
                  <small>후보 면적 {site.maxAreaM2.toLocaleString('ko-KR')} m²</small>
                  <button className="cistern-locate" onClick={() => onLocate(site)}>
                    <MapPin size={13} />
                    지도에서 보기
                  </button>
                </>
              ) : (
                <p>지도 또는 위치 목록에서 선택</p>
              )}
            </section>
          );
        })}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (s.valid) void s.save();
        }}
      >
        <fieldset disabled={s.busy}>
          <legend>탱크 설계</legend>
          {(
            [
              ['capture', '집수 면적 (m²)', s.roof?.maxAreaM2, '0.01'],
              ['area', '내부 수면적 (m²)', s.ground?.maxAreaM2, '0.01'],
              ['depth', '저류 깊이 (m)', 100, '0.001'],
            ] as const
          ).map(([key, label, max, step]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                min={step}
                max={max}
                step={step}
                required
                value={s[key]}
                onChange={(e) => s.edit(key, e.target.value)}
              />
            </label>
          ))}
          <strong>
            설계 용량{' '}
            {capacity > 0 && Number.isFinite(capacity)
              ? capacity.toLocaleString('ko-KR', { maximumFractionDigits: 4 })
              : '—'}{' '}
            m³
          </strong>
        </fieldset>
        <fieldset disabled={s.busy}>
          <legend>탱크 모양 · 위치</legend>
          {(
            [
              ['width', '내부 폭 (m)', 0.01, 10000, '0.01'],
              ['wall', '벽 두께 (m)', 0.001, 10, '0.001'],
              ['east', '동쪽 이동 (m)', -100000, 100000, '0.001'],
              ['north', '북쪽 이동 (m)', -100000, 100000, '0.001'],
              ['rotation', '회전 (°)', 0, 359.99, '0.01'],
            ] as const
          ).map(([key, label, min, max, step]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                min={min}
                max={max}
                step={step}
                required
                value={s.layoutFields[key]}
                onChange={(e) => s.editLayout(key, e.target.value)}
              />
            </label>
          ))}
          {s.geometry && (
            <p className="cistern-layout-summary">
              내부 길이{' '}
              {s.geometry.internalLengthM.toLocaleString('ko-KR', { maximumFractionDigits: 3 })}m
              <br />
              외곽{' '}
              {s.geometry.outerWidthM.toLocaleString('ko-KR', {
                maximumFractionDigits: 3,
              })}{' '}
              × {s.geometry.outerLengthM.toLocaleString('ko-KR', { maximumFractionDigits: 3 })}m
            </p>
          )}
          {s.geometry && (
            <p role={s.geometry.contained ? 'status' : 'alert'}>
              {s.geometry.contained
                ? '공개 지상 경계 안에 배치됨'
                : '탱크 외곽이 공개 지상 경계를 벗어납니다. 폭·위치·회전을 조절해 주세요.'}
            </p>
          )}
        </fieldset>
        <p className="micro-note">
          후보 중심에서 이동 · 지도 가로축 0°. 지도에는 저류공간과 벽체의 설계 범위를 표시합니다.
          기초·여유고·실제 홈통·배수 연결은 포함하지 않습니다.
        </p>
        {s.allowed ? (
          <button
            className="solid-button shared-install"
            disabled={s.busy || !s.valid || s.loading || s.plans.length >= 20}
          >
            {s.busy ? '저장 중…' : '지도 계획 저장'}
          </button>
        ) : (
          <button type="button" className="solid-button shared-install" onClick={onLogin}>
            로그인하고 계획 저장
          </button>
        )}
      </form>
      <p className="cistern-plan-status">
        설계 초안 · 위치 예약 및 설치 없음 · 예산·점수 변동 없음
      </p>
      {s.error && (
        <p role="alert">
          {s.error}
          <button onClick={s.retry} disabled={s.busy}>
            다시 조회
          </button>
        </p>
      )}
      {s.saved && (
        <>
          <p role="status">지도 계획 저장됨 · 두 위치의 원자료 버전 보존</p>
          <CisternReferenceCosts costing={s.saved.snapshot.referenceCosts} />
        </>
      )}
      <section className="cistern-plan-history">
        <h3>
          내 지도 계획 <small>{s.plans.length}/20</small>
        </h3>
        {s.loading ? (
          <p role="status">저장한 계획 조회 중…</p>
        ) : s.plans.length === 0 ? (
          <p>저장한 계획이 없습니다.</p>
        ) : (
          s.plans.map((plan) => (
            <div key={plan.id}>
              <button
                disabled={s.busy}
                onClick={() => {
                  s.restore(plan);
                  onLocate(plan.snapshot.roof);
                }}
              >
                {plan.snapshot.roof.name} → {plan.snapshot.ground.name}
                <small>
                  {plan.snapshot.capacityM3.toLocaleString('ko-KR')} m³ ·{' '}
                  {new Date(plan.createdAt).toLocaleDateString('ko-KR')}
                </small>
              </button>
              <button
                disabled={s.busy}
                aria-label={`${plan.snapshot.roof.name} 계획 삭제`}
                onClick={() => void s.remove(plan)}
              >
                삭제
              </button>
            </div>
          ))
        )}
      </section>
    </aside>
  );
}
