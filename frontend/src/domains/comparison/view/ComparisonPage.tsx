import { sameMapModels } from '../../game/service/modelFamilyService';
import { useEffect, useState } from 'react';
import { ArrowUpRight, Download, Play } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { RainfallCatalog, Version } from '../../game/entity/game';
import { rainDate } from '../../game/view/RainfallSelector';
import { format, won } from '../../game/service/gameService';
import { useComparison } from '../controller/useComparison';
import { comparisonState, jobStateNames } from '../service/comparisonService';

export function ComparisonPage({
  account,
  version,
  catalog,
  onOpen,
  onStudio,
}: {
  account: Account | null;
  version: Version | null;
  catalog: RainfallCatalog;
  onOpen: (id: string) => void;
  onStudio: () => void;
}) {
  const c = useComparison(account?.role === 'MEMBER'),
    [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    setSelected(
      sameMapModels(catalog, version?.modelHash)
        .filter((m) => m.modelHash !== version?.modelHash)
        .slice(0, 3)
        .map((m) => m.modelHash)
    );
  }, [version?.id, catalog]);
  const detail = c.detail;
  return (
    <section className="full-page comparison-page">
      <div className="page-eyebrow">
        RAINFALL COMPARISON <span>MY EXPERIMENTS</span>
      </div>
      <h1>
        내 배치 하나로,
        <br />
        여러 날의 비를 살피다.
      </h1>
      <p className="lead">
        같은 시설과 비용을 유지하고 강우 입력만 바꿉니다.
        <br />각 계산은 별도 버전으로 남고, 기록을 다시 열어 검토할 수 있습니다.
      </p>
      {!account ? (
        <div className="scope-note">로그인한 뒤 설계실에서 배치를 저장해 주세요.</div>
      ) : (
        <>
          {c.error && (
            <p className="comparison-error" role="alert">
              {c.error}
            </p>
          )}
          <div className="comparison-create">
            <div>
              <h2>비교할 저장 버전</h2>
              {version ? (
                <>
                  <p>
                    <b>
                      버전 {version.revision} · {won(version.cost)}
                    </b>
                  </p>
                  <p>
                    {version.placements.length}개 시설 ·{' '}
                    {new Date(version.createdAt).toLocaleString('ko-KR', {
                      timeZone: 'Asia/Seoul',
                    })}{' '}
                    저장
                  </p>
                  <small>지금 편집 중인 내용이 아닌 이 저장 버전을 복사합니다.</small>
                </>
              ) : (
                <p>설계실에서 저장하거나 기존 설계를 불러오면 비교할 수 있습니다.</p>
              )}
              <button className="text-button" onClick={onStudio}>
                설계실로 이동 <ArrowUpRight size={14} />
              </button>
            </div>
            <fieldset disabled={!version || c.busy}>
              <legend>비교 강우 2–3개 선택</legend>
              {sameMapModels(catalog, version?.modelHash).map((m) => (
                <label key={m.modelHash}>
                  <input
                    type="checkbox"
                    checked={selected.includes(m.modelHash)}
                    disabled={!selected.includes(m.modelHash) && selected.length >= 3}
                    onChange={(e) =>
                      setSelected((old) =>
                        e.target.checked
                          ? [...old, m.modelHash]
                          : old.filter((h) => h !== m.modelHash)
                      )
                    }
                  />
                  <span>
                    {m.rainfall.stationName} · {rainDate(m.rainfall.start)}
                    <small>
                      {format.format(m.rainfall.totalDepthMm)}mm
                      {m.modelHash === version?.modelHash ? ' · 원본과 같은 강우' : ''}
                    </small>
                  </span>
                </label>
              ))}
              <button
                className="outline-button"
                disabled={!version || selected.length < 2 || c.busy}
                onClick={() => {
                  if (version) void c.create(version.id, selected);
                }}
              >
                <Play size={14} />
                {c.busy ? '요청 처리 중' : '선택한 강우로 계산'}
              </button>
              <small>
                개인 계산 큐는 최대 3개입니다. 새 결과가 순위에 자동 제출되지는 않습니다.
              </small>
            </fieldset>
          </div>
          <div className="comparison-history">
            <label>
              저장한 비교 기록
              <select
                aria-label="저장한 비교 기록"
                value={detail?.id ?? ''}
                disabled={c.busy}
                onChange={(e) => {
                  if (e.target.value) void c.open(e.target.value);
                }}
              >
                <option value="">비교 기록 선택</option>
                {c.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} ·{' '}
                    {new Date(item.createdAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {detail && (
            <section aria-label="내 강우 비교 결과" className="comparison-detail">
              <div className="page-heading">
                <div>
                  <h2>{detail.title}</h2>
                  <p>
                    원본 버전 {detail.sourceVersion.revision} · {won(detail.sourceVersion.cost)} ·{' '}
                    {comparisonState(detail)}
                  </p>
                </div>
                <button
                  className="text-button"
                  disabled={c.busy}
                  onClick={() => void c.open(detail.id)}
                >
                  결과 새로고침
                </button>
              </div>
              <div
                className="reference-table-wrap"
                role="region"
                aria-label="내 강우별 결과표"
                tabIndex={0}
              >
                <table className="reference-results">
                  <thead>
                    <tr>
                      <th scope="col">관측 강우</th>
                      <th scope="col">상태</th>
                      <th scope="col">점수</th>
                      <th scope="col">기준 평가체적 m³</th>
                      <th scope="col">배치 평가체적 m³</th>
                      <th scope="col">종료 저류 m³</th>
                      <th scope="col">수지 오차</th>
                      <th scope="col">검토</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.jobs.map((j) => {
                      const m = catalog.models.find((m) => m.modelHash === j.modelHash);
                      return (
                        <tr key={j.id}>
                          <th scope="row">
                            {m
                              ? `${m.rainfall.stationName} · ${rainDate(m.rainfall.start)}`
                              : '과거 등록 강우'}
                            <small>
                              {m
                                ? `${format.format(m.rainfall.totalDepthMm)}mm`
                                : '저장된 입력에서 확인'}
                            </small>
                          </th>
                          <td>
                            {jobStateNames[j.state]}
                            {j.errorCode && (
                              <small className="comparison-error">계산 실패 · 다시 검토 필요</small>
                            )}
                          </td>
                          <td>
                            <b>{j.result ? format.format(j.result.score) : '—'}</b>
                          </td>
                          <td>
                            {j.result ? format.format(j.result.baseline.accountedDischargeM3) : '—'}
                          </td>
                          <td>
                            {j.result ? format.format(j.result.strategy.accountedDischargeM3) : '—'}
                          </td>
                          <td>
                            {j.result ? format.format(j.result.strategy.finalStorageM3) : '—'}
                          </td>
                          <td>
                            {j.result
                              ? j.result.strategy.runoffContinuityPercent.toFixed(4) + '%'
                              : '—'}
                          </td>
                          <td>
                            <button className="text-button" onClick={() => onOpen(j.strategyId)}>
                              설계 열기
                            </button>
                            {j.state === 'SUCCEEDED' && (
                              <a
                                className="comparison-bundle"
                                href={'/api/v1/simulations/' + j.id + '/bundle'}
                              >
                                <Download size={13} /> 재현 ZIP
                              </a>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="comparison-scope">
                점수는 각 강우의 시설 없는 기준안과 비교한 평가체적 감소율입니다. 강우별 점수를
                합산하지 않습니다. 실제 유출 관측으로 검증한 결과가 아니며, 종료 저류량과 관측 창
                길이를 함께 살펴야 합니다.
              </p>
            </section>
          )}
          {!detail && !c.items.length && (
            <p className="comparison-empty">
              아직 저장한 비교가 없습니다. 위에서 강우를 골라 첫 비교를 시작하세요.
            </p>
          )}
        </>
      )}
    </section>
  );
}
