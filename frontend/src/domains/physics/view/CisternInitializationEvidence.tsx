import type { CisternInitializationData } from '../dto/cisternInitializationDto';
import { InitializationEvidence } from './InitializationEvidence';
import { physicalAmount as amount } from '../service/physicalValueFormat';

export function CisternInitializationEvidence({ value }: { value: CisternInitializationData }) {
  return (
    <section className="initialization-sensitivity" aria-label="이용조 시작 저류 비교 결과">
      <h4>빈 이용조와 가득 찬 이용조의 차이</h4>
      <p>
        집수 지붕 {amount(value.areaM2)}㎡ · 이용조 용량 {amount(value.capacityM3)}㎥
      </p>
      <p>
        두 상태는 선행 7일 계산을 시작할 때의 조건입니다. 같은 강우·기상을 계산한 뒤 사건 시작의
        저류와 사건 전체 결과를 비교합니다. 사건 직전에 탱크를 비우거나 채우지 않습니다.
      </p>
      <p>
        평가 기간:{' '}
        {new Date(value.evaluationStart).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
        {' ~ '}
        {new Date(value.evaluationEnd).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST
      </p>
      {value.status === 'INCOMPLETE' && (
        <p role="status">일부 조건의 계산이 완료되지 않았습니다. 실패를 0으로 처리하지 않습니다.</p>
      )}
      {value.comparisons.map(({ operation, comparison }) => {
        const demand = operation === 'LITERATURE_DEMAND';
        const cases = value.cases
          .filter((c) => c.operation === operation)
          .sort((a, b) => a.seedSaturationPercent - b.seedSaturationPercent);
        const demandCase = cases.find((c) => c.status === 'SUCCEEDED' && c.demand);
        const demandEvidence = demandCase?.status === 'SUCCEEDED' ? demandCase.demand : null;
        type Case = (typeof cases)[number];
        const rows: {
          label: string;
          unit: string;
          get: (c: Extract<Case, { status: 'SUCCEEDED' }>) => number | null;
        }[] = [
          {
            label: '선행 계산 시작의 저류',
            unit: '㎥',
            get: (c) => c.nativeSeedStorageM3,
          },
          { label: '7일 후 사건 시작 저류', unit: '㎥', get: (c) => c.tank.initialStorageM3 },
          { label: '사건 종료 저류', unit: '㎥', get: (c) => c.tank.finalStorageM3 },
          { label: '사건 중 이용조 유입', unit: '㎥', get: (c) => c.tank.inflowM3 },
          { label: '사건 중 월류', unit: '㎥', get: (c) => c.tank.overflowM3 },
          ...(demand
            ? [
                {
                  label: '가정 수요',
                  unit: 'L',
                  get: (c: Extract<Case, { status: 'SUCCEEDED' }>) =>
                    c.demand ? c.demand.demandM3 * 1000 : null,
                },
                {
                  label: '잠재 공급',
                  unit: 'L',
                  get: (c: Extract<Case, { status: 'SUCCEEDED' }>) =>
                    c.demand ? c.demand.suppliedM3 * 1000 : null,
                },
                {
                  label: '부족량',
                  unit: 'L',
                  get: (c: Extract<Case, { status: 'SUCCEEDED' }>) =>
                    c.demand ? c.demand.unmetDemandM3 * 1000 : null,
                },
              ]
            : [
                {
                  label: '사건 중 자연배수',
                  unit: '㎥',
                  get: (c: Extract<Case, { status: 'SUCCEEDED' }>) => c.tank.outflowM3,
                },
              ]),
          { label: '물수지 잔차', unit: '㎥', get: (c) => c.tank.balanceResidualM3 },
        ];
        return (
          <div key={operation}>
            <h5>{demand ? '문헌 수요에 따른 일정 인출' : '자연배수 운전'}</h5>
            {demandEvidence && (
              <p>
                <a href={demandEvidence.source.url} target="_blank" rel="noopener noreferrer">
                  {demandEvidence.source.publicationYear}년 문헌 사례
                </a>
                의 수요를 지붕 면적에 비례시킨 하루 {amount(demandEvidence.demandRateM3Day * 1000)}
                L를 일중 균등하게 인출하는 가정입니다. 실제 건물 사용량은 확인되지 않았습니다.
              </p>
            )}
            {comparison.status === 'INCOMPLETE' && (
              <p>이 운전 조건의 초기 저류 차이는 비교 보류입니다.</p>
            )}
            <table>
              <caption>{demand ? '수요 운전' : '자연배수'} · 초기 저류 조건별 결과</caption>
              <thead>
                <tr>
                  <th scope="col">계산 지표</th>
                  {cases.map((c) => (
                    <th scope="col" key={c.seedSaturationPercent}>
                      {c.seedSaturationPercent === 0 ? '빈 이용조 시작' : '가득 찬 이용조 시작'}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.label}>
                    <th scope="row">
                      {r.label}
                      <small>{r.unit}</small>
                    </th>
                    {cases.map((c) => (
                      <td key={c.seedSaturationPercent}>
                        {c.status === 'FAILED'
                          ? '계산 실패'
                          : r.get(c) === null
                            ? '미산정'
                            : amount(r.get(c)!)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {comparison.status !== 'INCOMPLETE' && (
              <p>
                가득 찬 상태로 시작한 조건의 사건 시작 저류가 빈 상태보다{' '}
                {amount(comparison.seedDifferences[0].wetMinusDry.initialLidStorageM3!)}㎥ 차이
                납니다.
              </p>
            )}
          </div>
        );
      })}
      <p>
        수요 공급은 문헌 가정에 따른 계산량이며 실제 재이용 관측량이 아닙니다. 두 운전 결과와 초기
        저류 차이를 일반 점수에 더하지 않습니다.
      </p>
      <details>
        <summary>초기 저류 근거와 조건별 재현 정보</summary>
        <p>
          <a href={value.seedEvidence.url} target="_blank" rel="noopener noreferrer">
            EPA SWMM의 초기 저류 설정
          </a>
        </p>
        {value.cases.map((c) => (
          <div key={`${c.operation}:${c.seedSaturationPercent}`}>
            <h5>
              {c.operation === 'NATURAL_DRAIN' ? '자연배수' : '수요 운전'} ·{' '}
              {c.seedSaturationPercent === 0 ? '빈 이용조' : '가득 찬 이용조'}
            </h5>
            {c.status === 'SUCCEEDED' ? (
              <InitializationEvidence value={c.initialization} />
            ) : (
              <p>계산 실패 · 차이 미산정</p>
            )}
          </div>
        ))}
        {value.limitations.map((text) => (
          <p key={text}>{text}</p>
        ))}
        <p className="sensitivity-hash">입력 SHA-256 · {value.inputSha256}</p>
        <p>재현 자료의 sensitivity 폴더에 운전·초기 저류 조건별 원 입력과 계산 결과가 있습니다.</p>
      </details>
    </section>
  );
}
