package io.waterleague.common.security;

import io.waterleague.common.exception.*;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.*;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.ObjectMapper;

public class RequestSizeFilter extends OncePerRequestFilter {
  private final ObjectMapper json;

  public RequestSizeFilter(ObjectMapper j) {
    json = j;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest req, HttpServletResponse res, FilterChain chain)
      throws IOException, ServletException {
    if (!java.util.Set.of("POST", "PUT", "PATCH").contains(req.getMethod())) {
      chain.doFilter(req, res);
      return;
    }
    int max = 65536;
    byte[] body =
        req.getContentLengthLong() > max
            ? new byte[max + 1]
            : req.getInputStream().readNBytes(max + 1);
    if (body.length > max) {
      res.setStatus(413);
      res.setContentType("application/problem+json");
      json.writeValue(res.getWriter(), ProblemFactory.create(ErrorCode.REQUEST_TOO_LARGE, req));
      return;
    }
    chain.doFilter(
        new HttpServletRequestWrapper(req) {
          @Override
          public ServletInputStream getInputStream() {
            var input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
              public int read() {
                return input.read();
              }

              public boolean isFinished() {
                return input.available() == 0;
              }

              public boolean isReady() {
                return true;
              }

              public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException("동기 JSON 요청만 지원");
              }
            };
          }

          @Override
          public BufferedReader getReader() {
            return new BufferedReader(
                new InputStreamReader(getInputStream(), java.nio.charset.StandardCharsets.UTF_8));
          }
        },
        res);
  }
}
