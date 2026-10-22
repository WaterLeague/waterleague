import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Expand, X } from 'lucide-react';

export type HomeGameImageProps = {
  src: string;
  alt: string;
  width: number;
  height: number;
  caption: string;
};

function ImageDialog({ image, onClose }: { image: HomeGameImageProps; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    close.current?.focus();
    return () => element?.close();
  }, []);
  const dismiss = () => {
    dialog.current?.close();
    onClose();
  };
  return (
    <dialog
      ref={dialog}
      className="home-image-dialog site-dialog"
      aria-label={image.caption}
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
    >
      <div className="home-image-dialog-heading">
        <span>{image.caption}</span>
        <a href={image.src} target="_blank" rel="noopener noreferrer" className="home-text-link">
          원본 보기 <ArrowUpRight size={15} />
        </a>
        <button
          ref={close}
          className="icon-button"
          aria-label="게임 화면 크게 보기 닫기"
          onClick={dismiss}
        >
          <X size={22} />
        </button>
      </div>
      <img src={image.src} alt={image.alt} width={image.width} height={image.height} />
    </dialog>
  );
}

export function HomeGameImage(image: HomeGameImageProps) {
  const [expanded, setExpanded] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  return (
    <figure className="home-game-image">
      <button
        type="button"
        ref={opener}
        className="home-game-image-open"
        aria-label={`${image.caption} 크게 보기`}
        aria-haspopup="dialog"
        onClick={() => setExpanded(true)}
      >
        <img
          src={image.src}
          alt={image.alt}
          width={image.width}
          height={image.height}
          loading="lazy"
          decoding="async"
        />
        <span className="home-image-expand">
          <Expand size={15} /> 크게 보기
        </span>
      </button>
      <figcaption>{image.caption}</figcaption>
      {expanded && (
        <ImageDialog
          image={image}
          onClose={() => {
            setExpanded(false);
            opener.current?.focus();
          }}
        />
      )}
    </figure>
  );
}
