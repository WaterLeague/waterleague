if (!import.meta.env.DEV || !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
  throw new Error('로컬 전달 검사 전용');

export function designMock(initial, sites, storageKey) {
  const blank = {
    eventId: initial.eventId,
    revision: 0,
    snapshot: null,
    snapshotSha256: null,
    createdAt: null,
  };
  let saved = storageKey
    ? (JSON.parse(sessionStorage.getItem(storageKey) ?? 'null') ?? initial)
    : initial;
  const replies = new Map();
  let loseNext = false;
  const history = [];
  const response = (body, status = 200) => Response.json(body, { status });
  return {
    loseReply: () => {
      loseNext = true;
    },
    history,
    read: () => saved,
    reset: () => {
      saved = initial;
      if (storageKey) sessionStorage.removeItem(storageKey);
    },
    async fetch(url, init = {}) {
      const path = new URL(String(url), location.href).pathname;
      if (path !== '/api/v1/historical/designs/' + initial.eventId) return null;
      if ((init.method ?? 'GET') === 'GET') return response(saved ?? blank);
      if (init.method !== 'PUT') throw new Error('QA 설계 외 쓰기 거부');
      const body = JSON.parse(init.body);
      history.push(body);
      if (replies.has(body.requestKey)) return response(replies.get(body.requestKey));
      if (body.baseRevision !== saved.revision)
        return response(
          {
            code: 'HISTORICAL_DESIGN_CONFLICT',
            title: '다른 화면에서 설계가 변경되었습니다. 저장된 설계를 다시 불러와 주세요',
          },
          409
        );
      const placements = body.placements.map((item) => {
        const site = sites.find(
          (s) => s.districtId === item.districtId && s.cellId === item.cellId
        );
        if (!site) throw new Error('공개 원본 후보 외 QA 입력 거부');
        return {
          item,
          site,
          cost: item.areaM2 * site.unitCosts[item.facilityType],
          rainfallModelHash: 'a'.repeat(64),
        };
      });
      saved = {
        eventId: initial.eventId,
        revision: saved.revision + 1,
        snapshotSha256: 'b'.repeat(64),
        createdAt: new Date().toISOString(),
        snapshot: {
          schemaVersion: 1,
          eventId: initial.eventId,
          elapsedSeconds: body.elapsedSeconds,
          placements,
        },
      };
      replies.set(body.requestKey, saved);
      if (storageKey) sessionStorage.setItem(storageKey, JSON.stringify(saved));
      if (loseNext) {
        loseNext = false;
        throw new TypeError('저장 응답 유실 시험');
      }
      return response(saved);
    },
  };
}
