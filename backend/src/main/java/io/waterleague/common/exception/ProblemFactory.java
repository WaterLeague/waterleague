package io.waterleague.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ProblemDetail;
import java.net.URI;

public final class ProblemFactory {
    private ProblemFactory() { }
    public static ProblemDetail create(ErrorCode code, HttpServletRequest request) {
        var problem = ProblemDetail.forStatusAndDetail(code.status(), code.title());
        problem.setType(URI.create("urn:waterleague:problem:" + code.name().toLowerCase(java.util.Locale.ROOT).replace('_', '-')));
        problem.setTitle(code.title());
        problem.setProperty("code", code.name());
        problem.setProperty("traceId", request.getAttribute("traceId"));
        return problem;
    }
}
