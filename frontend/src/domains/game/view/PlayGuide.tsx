import { ArrowRight, X } from 'lucide-react';

const steps = ['구역 선택', '시설·면적 확정', '계산·비교'];

export function PlayGuide({
  step,
  pending,
  signedIn,
  currentResult,
  onChoose,
  onEdit,
  onCalculate,
  onClose,
}: {
  step: number;
  pending: 'QUEUED' | 'RUNNING' | 'REQUEST' | null;
  signedIn: boolean;
  currentResult: boolean;
  onChoose: () => void;
  onEdit: () => void;
  onCalculate: () => void;
  onClose: () => void;
}) {
  const descriptions = [
    '지도에 표시된 구역을 고르세요. 구역 목록과 2D 평면도에서도 선택할 수 있습니다.',
    '시설과 면적을 정한 뒤 배치 버튼으로 확정하세요. 미리보기는 예산과 계산에 포함되지 않습니다.',
    pending === 'REQUEST'
      ? '저장·요청을 처리하고 있습니다. 완료 후 계속 진행하세요.'
      : pending === 'QUEUED'
        ? '계산 순서를 기다리고 있습니다. 완료되면 결과로 이동합니다.'
        : pending === 'RUNNING'
          ? '서버에서 계산하고 있습니다. 완료되면 결과로 이동합니다.'
          : currentResult
            ? '현재 배치의 결과가 있습니다. 한 곳씩 바꾸어 다시 계산하고 같은 강우에서 비교해 보세요.'
            : `확정한 배치를 시설 없는 기준안과 비교합니다.${signedIn ? '' : ' 계산은 로그인 후 가능합니다. 배치는 유지됩니다.'}`,
  ];
  return (
    <section id="play-guide" className="play-guide" aria-labelledby="play-guide-title">
      <div className="play-guide-title">
        <b id="play-guide-title">첫 도전 안내</b>
        <button className="icon-button" aria-label="플레이 안내 접기" onClick={onClose}>
          <X size={16} />
        </button>
      </div>
      <ol>
        {steps.map((label, index) => (
          <li key={label} aria-current={step === index ? 'step' : undefined}>
            <span>{`0${index + 1}`}</span>
            {label}
          </li>
        ))}
      </ol>
      <div className="play-guide-next">
        <p>{descriptions[step]}</p>
        <button
          className="text-button"
          disabled={!!pending}
          onClick={[onChoose, onEdit, onCalculate][step]}
        >
          {step === 0
            ? '구역 목록 열기'
            : step === 1
              ? '면적 입력으로 이동'
              : currentResult
                ? '결과 다시 보기'
                : '계산 버튼으로 이동'}{' '}
          <ArrowRight size={14} />
        </button>
      </div>
    </section>
  );
}
