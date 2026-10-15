package io.waterleague.common.exception;

public class DomainException extends RuntimeException {
    private final ErrorCode code;
    public DomainException(ErrorCode code) { super(code.title()); this.code = code; }
    public ErrorCode code() { return code; }
}
