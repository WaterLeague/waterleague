import { useEffect, useRef, useState, type ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import { useServerConnection } from '../controller/useServerConnection';
import { ServerConnectedContext } from '../controller/serverConnectionContext';
import './server-connection.css';

export function ServerConnectionPage({
  initial,
  checking,
  retry,
}: {
  initial: boolean;
  checking: boolean;
  retry: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  useEffect(() => {
    if (initial) return;
    const focusHeading = () => heading.current?.focus();
    focusHeading();
    document.addEventListener('fullscreenchange', focusHeading);
    return () => document.removeEventListener('fullscreenchange', focusHeading);
  }, [initial]);
  return (
    <dialog
      ref={dialog}
      className="server-connection-page"
      aria-labelledby="server-connection-title"
      onCancel={(event) => event.preventDefault()}
    >
      <header className="server-connection-brand">
        <img src="/brand/wordmark.png" alt="Water League" width="125" height="52" />
      </header>
      <main className="server-connection-content">
        <div className="server-connection-friends" role="img" aria-label="여울이와 가람이">
          <img
            className="connection-otter"
            src="/brand/otter.png"
            alt=""
            width="300"
            height="299"
          />
          <img
            className="connection-bird"
            src="/brand/kingfisher.png"
            alt=""
            width="1383"
            height="1137"
          />
        </div>
        <h1 id="server-connection-title" ref={heading} tabIndex={-1}>
          {initial ? '서버에 연결하고 있어요' : '서버와 연결이 끊겼어요'}
        </h1>
        <p>
          {initial
            ? '여울이와 가람이가 준비하고 있어요.'
            : '여울이와 가람이가 잠시 기다리고 있어요.'}
          <br />
          {initial ? '잠시만 기다려 주세요.' : '연결이 돌아오면 이전 화면으로 돌아갑니다.'}
        </p>
        {!initial && (
          <button
            type="button"
            className="server-connection-retry"
            onClick={retry}
            disabled={checking}
          >
            <RefreshCw
              size={17}
              aria-hidden="true"
              className={checking ? 'is-checking' : undefined}
            />
            {checking ? '연결 확인 중' : '다시 연결'}
          </button>
        )}
        <p className="server-connection-status" role="status">
          {checking ? '서버 응답을 기다리고 있습니다.' : '자동으로 연결 상태를 다시 확인합니다.'}
        </p>
      </main>
    </dialog>
  );
}

export function ServerConnectionBoundary({ children }: { children: ReactNode }) {
  const { status, checking, retry } = useServerConnection();
  const connected = status === 'connected';
  const [started, setStarted] = useState(false);
  useEffect(() => {
    if (connected) setStarted(true);
    else if (status === 'disconnected') {
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    }
  }, [connected, status]);
  return (
    <>
      {/* 지도를 해제하면 WebGL 문맥을 잃으므로 화면은 유지하고 재생만 정지한다. */}
      <ServerConnectedContext value={connected}>
        {(connected || started) && children}
      </ServerConnectedContext>
      {!connected && (
        <ServerConnectionPage initial={status === 'checking'} checking={checking} retry={retry} />
      )}
    </>
  );
}
