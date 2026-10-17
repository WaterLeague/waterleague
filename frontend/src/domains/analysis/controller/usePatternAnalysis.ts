import { useEffect, useRef, useState } from 'react';
import { analyzePatterns } from '../repository/analysisRepository';
import { patternFingerprint } from '../service/analysisService';
import type { PatternAnalysis } from '../entity/analysis';
import { errorMessage } from '../../../shared/exception/ApiError';
export function usePatternAnalysis(jobIds: string[], topK: number) {
  const fingerprint = patternFingerprint(jobIds, topK);
  const [result, setResult] = useState<{ fingerprint: string; value: PatternAnalysis } | null>(
      null
    ),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const alive = useRef(true),
    epoch = useRef(0),
    running = useRef(false),
    latest = useRef(fingerprint);
  latest.current = fingerprint;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      epoch.current++;
    };
  }, []);
  useEffect(() => {
    setResult(null);
    setError('');
  }, [fingerprint]);
  async function run() {
    if (running.current) return;
    running.current = true;
    const token = ++epoch.current,
      requested = fingerprint;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const value = await analyzePatterns(jobIds, topK);
      if (alive.current && token === epoch.current && requested === latest.current)
        setResult({ fingerprint: requested, value });
    } catch (e) {
      if (alive.current && token === epoch.current && requested === latest.current)
        setError(errorMessage(e));
    } finally {
      if (alive.current && token === epoch.current) {
        running.current = false;
        setBusy(false);
      }
    }
  }
  // 재방문 시 이전 동의로 계산한 집계를 남기지 않고 현재 권한으로 다시 조회.
  useEffect(() => {
    const clear = () => {
      epoch.current++;
      running.current = false;
      setBusy(false);
      setResult(null);
    };
    window.addEventListener('focus', clear);
    return () => window.removeEventListener('focus', clear);
  }, []);
  return { result: result?.fingerprint === fingerprint ? result.value : null, busy, error, run };
}
