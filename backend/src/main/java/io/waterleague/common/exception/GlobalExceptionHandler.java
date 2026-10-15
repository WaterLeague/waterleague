package io.waterleague.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class GlobalExceptionHandler {
  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  @ExceptionHandler(DomainException.class)
  ResponseEntity<ProblemDetail> domain(DomainException error, HttpServletRequest request) {
    return response(error.code(), request);
  }

  @ExceptionHandler({
    MethodArgumentNotValidException.class,
    org.springframework.web.method.annotation.HandlerMethodValidationException.class,
    jakarta.validation.ConstraintViolationException.class,
    HttpMessageNotReadableException.class,
    MethodArgumentTypeMismatchException.class
  })
  ResponseEntity<ProblemDetail> invalid(Exception error, HttpServletRequest request) {
    return response(ErrorCode.REQUEST_INVALID, request);
  }

  @ExceptionHandler(NoResourceFoundException.class)
  ResponseEntity<ProblemDetail> missing(HttpServletRequest request) {
    return response(ErrorCode.RESOURCE_NOT_FOUND, request);
  }

  @ExceptionHandler(Exception.class)
  ResponseEntity<ProblemDetail> unknown(Exception error, HttpServletRequest request) {
    // 예외 원문에 입력·비밀값이 포함될 수 있어 유형과 추적 ID만 기록한다.
    log.error(
        "Unhandled error type={} traceId={}",
        error.getClass().getSimpleName(),
        request.getAttribute("traceId"));
    return response(ErrorCode.INTERNAL_ERROR, request);
  }

  private ResponseEntity<ProblemDetail> response(ErrorCode code, HttpServletRequest request) {
    return ResponseEntity.status(code.status())
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(ProblemFactory.create(code, request));
  }
}
