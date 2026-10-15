package io.waterleague.common.security;

import io.waterleague.account.repository.AccountRepository;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionPolicyFilter extends OncePerRequestFilter {
  private final AccountRepository accounts;

  public SessionPolicyFilter(AccountRepository a) {
    accounts = a;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest req, HttpServletResponse res, FilterChain chain)
      throws ServletException, IOException {
    var auth = SecurityContextHolder.getContext().getAuthentication();
    if (auth != null && auth.isAuthenticated()) {
      var session = req.getSession(false);
      var account = accounts.byUsername(auth.getName());
      Object at = session == null ? null : session.getAttribute("authenticatedAt");
      boolean valid =
          account.isPresent()
              && account.get().usable()
              && at instanceof Long since
              && System.currentTimeMillis() - since < 8 * 60 * 60 * 1000L;
      if (valid) {
        var a = account.get();
        valid =
            auth.getAuthorities().stream()
                    .anyMatch(r -> r.getAuthority().equals("ROLE_" + a.role()))
                && (a.organizationMember()
                    == auth.getAuthorities().stream()
                        .anyMatch(r -> r.getAuthority().equals("ORGANIZATION_MEMBER")))
                && (!a.requiresMfa() || Boolean.TRUE.equals(session.getAttribute("mfaVerified")));
      }
      if (!valid) {
        if (session != null) session.invalidate();
        SecurityContextHolder.clearContext();
      }
    }
    chain.doFilter(req, res);
  }
}
