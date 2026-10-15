package io.waterleague.common.exception;

import org.springframework.http.HttpStatus;

public enum ErrorCode {
    CREDENTIALS_INVALID(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호를 확인해 주세요"),
    ACCOUNT_UNAVAILABLE(HttpStatus.CONFLICT, "사용할 수 없는 아이디입니다"),
    RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS, "요청이 많습니다. 잠시 후 다시 시도해 주세요"),
    CONFLICT(HttpStatus.CONFLICT, "현재 상태에서 처리할 수 없습니다"),
    REQUEST_INVALID(HttpStatus.BAD_REQUEST, "요청 형식을 확인해 주세요"),
    AUTHENTICATION_REQUIRED(HttpStatus.UNAUTHORIZED, "로그인이 필요합니다"),
    ACCESS_DENIED(HttpStatus.FORBIDDEN, "접근 권한이 없습니다"),
    RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "자료를 찾을 수 없습니다"),
    MODEL_NOT_ELIGIBLE(HttpStatus.UNPROCESSABLE_ENTITY, "모델 검증이 필요합니다"),
    RESULT_QUALITY_FAILED(HttpStatus.UNPROCESSABLE_ENTITY, "계산 품질 검사를 통과하지 못했습니다"),
    PLACEMENT_INVALID(HttpStatus.UNPROCESSABLE_ENTITY, "설치 조건을 확인해 주세요"),
    BUDGET_EXCEEDED(HttpStatus.UNPROCESSABLE_ENTITY, "설치 예산을 초과했습니다"),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "요청을 처리하지 못했습니다");

    private final HttpStatus status;
    private final String title;
    ErrorCode(HttpStatus status, String title) { this.status = status; this.title = title; }
    public HttpStatus status() { return status; }
    public String title() { return title; }
}
