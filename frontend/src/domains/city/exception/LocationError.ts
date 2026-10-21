const messages = {
  UNSUPPORTED: '이 브라우저에서는 현재 위치를 확인할 수 없습니다.',
  INSECURE: '현재 위치는 보안 연결(HTTPS)에서 사용할 수 있습니다.',
  DENIED: '위치 권한이 꺼져 있습니다. 브라우저 설정에서 위치 접근을 허용해 주세요.',
  UNAVAILABLE: '현재 위치를 확인하지 못했습니다. 기기의 위치 설정을 확인해 주세요.',
  TIMEOUT: '위치 확인 시간이 초과되었습니다. 다시 시도해 주세요.',
  OUTSIDE_SEOUL: '현재 위치가 서울 밖입니다. 서울 안에서만 내 위치로 이동할 수 있습니다.',
  FAILED: '현재 위치로 이동하지 못했습니다. 잠시 후 다시 시도해 주세요.',
};

export class LocationError extends Error {
  constructor(readonly kind: keyof typeof messages) {
    super(messages[kind]);
    this.name = 'LocationError';
  }
}
