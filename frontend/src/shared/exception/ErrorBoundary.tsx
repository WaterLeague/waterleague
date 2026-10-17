import { Component } from 'react';
import type { ReactNode } from 'react';
export class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode; onError?: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError?.();
  }
  render() {
    return this.state.failed
      ? (this.props.fallback ?? (
          <div className="error-view">
            <h1>화면을 불러오지 못했습니다.</h1>
            <p>페이지를 새로고침해 다시 시도해 주세요.</p>
            <button onClick={() => location.reload()}>다시 불러오기</button>
          </div>
        ))
      : this.props.children;
  }
}
