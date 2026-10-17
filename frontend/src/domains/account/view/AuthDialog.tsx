import { useEffect, useRef, useState } from 'react';
import { DistrictFields } from '../../district/view/DistrictFields';
import type { AffiliationType } from '../../district/entity/district';
import { X, ArrowRight } from 'lucide-react';
import { authenticate, beginEnrollment, confirmEnrollment } from '../repository/accountRepository';
import { type Account, type MemberType, memberTypeNames } from '../entity/account';
import { ApiError } from '../../../shared/exception/ApiError';
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
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [memberType, setMemberType] = useState<MemberType>('PLAYER'),
    [organizationName, setOrganizationName] = useState(''),
    [purpose, setPurpose] = useState(''),
    [districtId, setDistrictId] = useState(''),
    [affiliationType, setAffiliationType] = useState<AffiliationType>('RESIDENT'),
    [enrollment, setEnrollment] = useState<{
      secret: string;
      issuer: string;
      accountName: string;
    } | null>(null);
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
      <p>우리 구에 시설을 설치하고 서울 주간 리그에 함께 도전하세요.</p>
      {!enrollment && (
        <div className="auth-tabs">
          <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>
            로그인
          </button>
          <button
            className={mode === 'register' ? 'active' : ''}
            onClick={() => setMode('register')}
          >
            회원 가입
          </button>
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            if (enrollment) {
              onSuccess(await confirmEnrollment(otp));
              onClose();
            } else {
              const account = await authenticate(mode, name, password, otp, {
                memberType,
                districtId,
                affiliationType,
                organizationName: memberType === 'PLAYER' ? '' : organizationName,
                purpose: memberType === 'PLAYER' ? '' : purpose,
              });
              if (account.approvalStatus === 'APPROVED') {
                onSuccess(account);
                onClose();
              } else {
                setNotice('가입 신청 접수 완료. 관리자가 소속과 이용 목적을 확인한 후 승인합니다.');
                setMode('login');
              }
            }
          } catch (e) {
            if (e instanceof ApiError && e.code === 'MFA_ENROLLMENT_REQUIRED') {
              try {
                setEnrollment(await beginEnrollment(name, password));
                setError('');
              } catch (setupError) {
                setError(errorMessage(setupError));
              }
            } else setError(errorMessage(e));
          } finally {
            setBusy(false);
            setPassword('');
            setOtp('');
          }
        }}
      >
        {!enrollment && (
          <>
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
            {mode === 'register' && (
              <>
                <label>
                  회원 유형
                  <select
                    value={memberType}
                    onChange={(e) => setMemberType(e.target.value as MemberType)}
                  >
                    {Object.entries(memberTypeNames).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <DistrictFields
                  districtId={districtId}
                  affiliationType={affiliationType}
                  onDistrict={setDistrictId}
                  onType={setAffiliationType}
                />
                {memberType !== 'PLAYER' && (
                  <>
                    <label>
                      소속 조직명
                      <input
                        required
                        maxLength={100}
                        value={organizationName}
                        onChange={(e) => setOrganizationName(e.target.value)}
                      />
                    </label>
                    <label>
                      이용 목적
                      <textarea
                        required
                        maxLength={2000}
                        rows={3}
                        value={purpose}
                        onChange={(e) => setPurpose(e.target.value)}
                        placeholder="리그 운영·연구 목적과 소속 확인에 필요한 설명"
                      />
                    </label>
                    <p className="footnote">
                      관리자 승인 후 인증 앱을 등록하면 이용할 수 있습니다. 신청 내용에 비밀번호나
                      비밀키를 적지 마세요.
                    </p>
                  </>
                )}
              </>
            )}
          </>
        )}
        {enrollment && (
          <div className="mfa-enrollment">
            <h3>인증 앱 연결</h3>
            <p>
              인증 앱에서 계정을 직접 추가하고 아래 등록키를 입력하세요. 시간 기반·6자리·30초·SHA1
              설정입니다.
            </p>
            <span>
              {enrollment.issuer} · {enrollment.accountName}
            </span>
            <code>{enrollment.secret}</code>
            <p>등록키는 본인만 보관하세요. 5분 안에 인증번호를 입력하면 연결이 완료됩니다.</p>
          </div>
        )}
        {mode === 'login' && (
          <label>
            {enrollment ? '등록 확인 인증번호' : '인증 앱 번호'}{' '}
            <input
              required={!!enrollment}
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              autoComplete="one-time-code"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="관리자·기업·기관·정부 회원 · 6자리"
            />
          </label>
        )}
        {notice && <p role="status">{notice}</p>}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button disabled={busy} className="primary-button" type="submit">
          {busy
            ? '확인 중'
            : enrollment
              ? '인증 앱 연결 완료'
              : mode === 'login'
                ? '로그인'
                : memberType === 'PLAYER'
                  ? '가입하고 시작'
                  : '가입 승인 신청'}
          <ArrowRight size={16} />
        </button>
      </form>
      <small>일반 플레이어는 즉시 가입, 기업·기관·정부 회원은 관리자 승인 후 이용합니다.</small>
    </dialog>
  );
}
