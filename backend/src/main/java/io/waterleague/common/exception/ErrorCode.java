package io.waterleague.common.exception;

import org.springframework.http.HttpStatus;

public enum ErrorCode {
  CREDENTIALS_INVALID(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호를 확인해 주세요"),
  ACCOUNT_NOT_APPROVED(HttpStatus.FORBIDDEN, "가입 승인 대기·반려 또는 이용 정지 상태입니다. 관리자 검토 후 이용할 수 있습니다"),
  MFA_ENROLLMENT_REQUIRED(HttpStatus.FORBIDDEN, "인증 앱 등록을 완료해 주세요"),
  ACCOUNT_UNAVAILABLE(HttpStatus.CONFLICT, "사용할 수 없는 아이디입니다"),
  RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS, "요청이 많습니다. 잠시 후 다시 시도해 주세요"),
  CONFLICT(HttpStatus.CONFLICT, "현재 상태에서 처리할 수 없습니다"),
  REQUEST_INVALID(HttpStatus.BAD_REQUEST, "요청 형식을 확인해 주세요"),
  REQUEST_TOO_LARGE(HttpStatus.CONTENT_TOO_LARGE, "요청 본문이 허용 크기를 초과했습니다"),
  AUTHENTICATION_REQUIRED(HttpStatus.UNAUTHORIZED, "로그인이 필요합니다"),
  ACCESS_DENIED(HttpStatus.FORBIDDEN, "접근 권한이 없습니다"),
  RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "자료를 찾을 수 없습니다"),
  MODEL_NOT_ELIGIBLE(HttpStatus.UNPROCESSABLE_ENTITY, "모델 검증이 필요합니다"),
  COMPARISON_INCOMPATIBLE(HttpStatus.UNPROCESSABLE_ENTITY, "강우 외의 모델 조건이 달라 동일 배치를 비교할 수 없습니다"),
  ANALYSIS_INCOMPATIBLE(HttpStatus.UNPROCESSABLE_ENTITY, "같은 모델의 유효한 제출 기록을 선택해 주세요"),
  SEARCH_SAMPLE_INSUFFICIENT(HttpStatus.UNPROCESSABLE_ENTITY, "서로 다른 물리 배치가 두 개 이상 필요합니다"),
  CANDIDATE_SPACE_EXHAUSTED(
      HttpStatus.UNPROCESSABLE_ENTITY, "정해진 탐색 횟수 안에 새 후보를 채우지 못했습니다. 예산과 후보 수를 조정해 주세요"),
  UTILIZATION_CONFLICT(HttpStatus.CONFLICT, "기존 요청 또는 최신 동의 상태를 확인해 주세요"),
  RESULT_QUALITY_FAILED(HttpStatus.UNPROCESSABLE_ENTITY, "계산 품질 검사를 통과하지 못했습니다"),
  PLACEMENT_INVALID(HttpStatus.UNPROCESSABLE_ENTITY, "설치 조건을 확인해 주세요"),
  BUDGET_EXCEEDED(HttpStatus.UNPROCESSABLE_ENTITY, "설치 예산을 초과했습니다"),
  SPATIAL_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "공간자료를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요"),
  SPATIAL_ACCESS_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "공간자료 서비스의 인증 설정 확인이 필요합니다"),
  SPATIAL_DATA_INVALID(HttpStatus.SERVICE_UNAVAILABLE, "공간자료의 좌표·응답 품질 검사를 통과하지 못했습니다"),
  LEAGUE_IMMUTABLE(HttpStatus.CONFLICT, "공개 상태 또는 규칙 버전을 확인해 주세요"),
  LEAGUE_CLOSED(HttpStatus.CONFLICT, "현재 제출을 받지 않는 리그입니다"),
  LEAGUE_RULES_MISMATCH(HttpStatus.UNPROCESSABLE_ENTITY, "리그의 모델·시설·실행 조건과 일치하지 않습니다"),
  LEAGUE_PARTICIPATION_CONFLICT(HttpStatus.CONFLICT, "참가 승인·팀 구성·최신 상태를 확인해 주세요"),
  LEAGUE_SUBMISSION_LIMIT(HttpStatus.CONFLICT, "이 리그의 제출 한도를 사용했습니다"),
  RAINFALL_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "실시간 강우를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요"),
  RAINFALL_ACCESS_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "실시간 강우 API 인증 설정 확인이 필요합니다"),
  RAINFALL_DATA_INVALID(HttpStatus.SERVICE_UNAVAILABLE, "실시간 강우 응답의 관측 시각·형식을 확인하지 못했습니다"),
  INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "요청을 처리하지 못했습니다");

  private final HttpStatus status;
  private final String title;

  ErrorCode(HttpStatus status, String title) {
    this.status = status;
    this.title = title;
  }

  public HttpStatus status() {
    return status;
  }

  public String title() {
    return title;
  }
}
