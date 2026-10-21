import { useEffect, useRef } from 'react';
import { ArrowUpRight, CloudRain, Sun, X } from 'lucide-react';
import { followLink } from '../../../shared/controller/useAppLocation';
import { homeModes } from '../service/homeContent';

export function GameStartDialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const firstMode = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    firstMode.current?.focus();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="home-start-dialog site-dialog"
      aria-labelledby="game-start-title"
      onCancel={onClose}
    >
      <button
        type="button"
        className="icon-button close"
        onClick={onClose}
        aria-label="게임 모드 선택 닫기"
      >
        <X size={20} />
      </button>

      <h2 id="game-start-title">게임 모드를 선택하세요</h2>
      <p>실시간 관측 강우로 경쟁하거나, 과거 호우로 설계를 실험하세요.</p>
      <div className="home-start-options">
        {homeModes.map((mode, index) => {
          const Icon = mode.id === 'weekly' ? Sun : CloudRain;
          return (
            <a
              key={mode.id}
              ref={index === 0 ? firstMode : undefined}
              href={mode.href}
              onClick={(event) => followLink(event, mode.href)}
            >
              <Icon size={28} aria-hidden="true" />
              <span className="home-eyebrow">{mode.tag}</span>
              <h3>{mode.title}</h3>
              <p>{mode.intro}</p>
              <small>
                {mode.id === 'weekly'
                  ? '지도 둘러보기 · 로그인 후 우리 구에 설치'
                  : '로그인 없이 체험 · 로그인 후 기록 제출'}
              </small>
              <span className="home-start-choice">
                시작하기 <ArrowUpRight size={18} aria-hidden="true" />
              </span>
            </a>
          );
        })}
      </div>
    </dialog>
  );
}
