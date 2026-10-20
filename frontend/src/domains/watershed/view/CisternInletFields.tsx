import type { CisternInletPipe } from '../dto/cisternDto';

export function CisternInletFields({
  value,
  onChange,
  kind = 'inlet',
}: {
  value?: CisternInletPipe | null;
  onChange: (value: CisternInletPipe | null) => void;
  kind?: 'inlet' | 'drain' | 'overflow';
}) {
  const inlet = kind === 'inlet';
  const label = inlet ? '집수 연결관' : kind === 'drain' ? '일반 배수 연결관' : '비상 배수 연결관';
  return (
    <fieldset>
      <legend>{label}</legend>
      <label>
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) =>
            onChange(
              e.target.checked
                ? {
                    lengthM: NaN,
                    diameterM: NaN,
                    roughness: NaN,
                    upstreamInvertM: NaN,
                    upstreamMaxDepthM: NaN,
                    downstreamInvertM: NaN,
                  }
                : null
            )
          }
        />
        관의 통수 용량·마찰·역류 계산
      </label>
      {value ? (
        <>
          <p>
            같은 기준면의 높이를 입력합니다. {inlet ? '집수 입구' : '배출구 뒤 접속부'}는 처음에
            비어 있고, 넘치면 효과 비교를 보류합니다. 관의 국부 손실·막힘·별도 역류 방지 장치는
            포함하지 않습니다.
          </p>
          <div className="watershed-inputs">
            {(
              [
                ['lengthM', '관 길이 (m)', 0.001, 10000],
                ['diameterM', '관 내부 직경 (m)', 0.001, 100],
                ['roughness', 'Manning 조도', 0.001, 1],
                [
                  'upstreamInvertM',
                  inlet ? '집수 입구 바닥 기준고 (m)' : '배출구 뒤 접속부 바닥 기준고 (m)',
                  -1000,
                  10000,
                ],
                [
                  'upstreamMaxDepthM',
                  inlet ? '집수 입구 월류 깊이 (m)' : '배출구 뒤 접속부 월류 깊이 (m)',
                  0.001,
                  100,
                ],
                [
                  'downstreamInvertM',
                  inlet ? '이용조 쪽 관 바닥 기준고 (m)' : '하류 절점 쪽 관 바닥 기준고 (m)',
                  -1000,
                  10000,
                ],
              ] as const
            ).map(([key, label, min, max]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min={min}
                  max={max}
                  step={0.001}
                  value={Number.isFinite(value[key]) ? value[key] : ''}
                  onChange={(e) => onChange({ ...value, [key]: e.target.valueAsNumber })}
                />
              </label>
            ))}
          </div>
        </>
      ) : (
        <p>
          {inlet
            ? '집수 유출을 이용조에 직접 연결합니다. 홈통·연결관의 통수 용량은 계산하지 않습니다.'
            : '배출구를 원 관망에 직접 연결합니다. 별도 접속관의 통수 용량·마찰은 계산하지 않습니다.'}
        </p>
      )}
    </fieldset>
  );
}
