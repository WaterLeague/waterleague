export class ApprovalDataError extends Error {
  constructor() {
    super('회원 신청 자료 형식을 확인할 수 없습니다.');
  }
}
