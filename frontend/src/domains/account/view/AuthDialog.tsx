import { useEffect, useRef, useState } from 'react';
import { X, ArrowRight } from 'lucide-react';
import { authenticate } from '../repository/accountRepository';
import type { Account } from '../entity/account';
import { errorMessage } from '../../../shared/exception/ApiError';
export function AuthDialog({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: (a: Account) => void;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login'),
    [name, setName] = useState(''),
    [password, setPassword] = useState(''),
    [otp, setOtp] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const ref = useRef<HTMLDialogElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    nameInput.current?.focus();
    return () => el?.close();
  }, []);
  return (
    <dialog ref={ref} aria-labelledby="auth-title" className="auth-dialog" onCancel={onClose}>
      <button className="icon-button close" aria-label="로그인 창 닫기" onClick={onClose}>
        <X size={20} />
      </button>
      <span className="eyebrow">WATER LEAGUE ACCOUNT</span>
      <h2 id="auth-title">
        {mode === 'login' ? '다시, 더 나은 설계로.' : '도시를 바꾸는 첫 설계.'}
      </h2>
      <p>나만의 설계를 저장하고 같은 조건에서 기록에 도전하세요.</p>
      <div className="auth-tabs">
        <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>
          로그인
        </button>
        <button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>
          플레이어 가입
        </button>
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            onSuccess(await authenticate(mode, name, password, otp));
            onClose();
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
            setPassword('');
            setOtp('');
          }
        }}
      >
        <label>
          아이디
          <input
            ref={nameInput}
            required
            pattern="[a-z0-9_]{4,32}"
            minLength={4}
            maxLength={32}
            autoComplete="username"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="영문 소문자·숫자·밑줄 4~32자"
          />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            required
            minLength={12}
            maxLength={128}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="12자 이상"
          />
        </label>
        {mode === 'login' && (
          <label>
            기관 인증번호{' '}
            <input
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              autoComplete="one-time-code"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="기관 계정만 입력 · 6자리"
            />
          </label>
        )}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button disabled={busy} className="primary-button" type="submit">
          {busy ? '확인 중' : mode === 'login' ? '로그인' : '가입하고 시작'}
          <ArrowRight size={16} />
        </button>
      </form>
      <small>기관 계정은 소속 확인 후 운영자가 별도로 승인합니다.</small>
    </dialog>
  );
}
