package io.waterleague.account.controller;

import io.waterleague.account.dto.AuthRequest;
import io.waterleague.account.dto.RegistrationRequest;
import io.waterleague.account.entity.Account;
import io.waterleague.account.mapper.AccountMapper;
import io.waterleague.account.service.AccountService;
import io.waterleague.account.view.AccountView;
import io.waterleague.common.exception.*;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
  private final AccountService accounts;
  private final RateLimitService rates;
  private final JsonService json;
  private final io.waterleague.account.service.InstitutionMfaService mfa;

  public AuthController(
      AccountService a,
      RateLimitService r,
      JsonService j,
      io.waterleague.account.service.InstitutionMfaService m) {
    accounts = a;
    rates = r;
    json = j;
    mfa = m;
  }

  @GetMapping("/csrf")
  public Map<String, String> csrf(CsrfToken token) {
    return Map.of("token", token.getToken(), "headerName", token.getHeaderName());
  }

  @PostMapping("/register")
  public AccountView register(
      @Valid @RequestBody RegistrationRequest dto,
      HttpServletRequest req,
      HttpServletResponse res) {
    rates.check("register:" + json.hash(req.getRemoteAddr()), 8, 3600);
    var a = accounts.register(dto);
    if (a.usable()) signIn(a, req, res);
    else logout(req, res);
    return AccountMapper.view(a);
  }

  @PostMapping("/login")
  public AccountView login(
      @Valid @RequestBody AuthRequest dto, HttpServletRequest req, HttpServletResponse res) {
    rates.check("login-ip:" + json.hash(req.getRemoteAddr()), 40, 900);
    rates.check("login-user:" + json.hash(dto.username()), 15, 900);
    var a = accounts.login(dto);
    if (a.requiresMfa()) {
      if (!mfa.enrolled(a.id())) throw new DomainException(ErrorCode.MFA_ENROLLMENT_REQUIRED);
      mfa.verify(a.id(), dto.otp());
    }
    signIn(a, req, res);
    return AccountMapper.view(a);
  }

  @GetMapping("/me")
  public AccountView me(Principal p) {
    return AccountMapper.view(accounts.current(p.getName()));
  }

  @PostMapping("/mfa/enrollment")
  public org.springframework.http.ResponseEntity<?> enrollment(
      @Valid @RequestBody AuthRequest dto, HttpServletRequest req, HttpServletResponse res) {
    rates.check("mfa-enroll:" + json.hash(req.getRemoteAddr()), 10, 900);
    rates.check("login-user:" + json.hash(dto.username()), 15, 900);
    var a = accounts.login(dto);
    if (!a.requiresMfa()) throw new DomainException(ErrorCode.ACCESS_DENIED);
    String secret = mfa.begin(a.id());
    var old = req.getSession(false);
    if (old != null) old.invalidate();
    SecurityContextHolder.clearContext();
    req.getSession().setAttribute("mfaEnrollmentUser", a.username());
    req.getSession().setAttribute("mfaEnrollmentAt", System.currentTimeMillis());
    rotateCsrf(req, res);
    return org.springframework.http.ResponseEntity.ok()
        .cacheControl(org.springframework.http.CacheControl.noStore())
        .body(
            Map.of(
                "secret",
                secret,
                "issuer",
                "WaterLeague",
                "accountName",
                a.username(),
                "expiresInSeconds",
                300));
  }

  public record MfaConfirmation(
      @jakarta.validation.constraints.NotNull
          @jakarta.validation.constraints.Pattern(regexp = "[0-9]{6}")
          String otp) {}

  @PostMapping("/mfa/confirm")
  public AccountView confirmMfa(
      @Valid @RequestBody MfaConfirmation dto, HttpServletRequest req, HttpServletResponse res) {
    var session = req.getSession(false);
    if (session == null
        || !(session.getAttribute("mfaEnrollmentAt") instanceof Long since)
        || System.currentTimeMillis() - since > 300000
        || !(session.getAttribute("mfaEnrollmentUser") instanceof String username))
      throw new DomainException(ErrorCode.AUTHENTICATION_REQUIRED);
    var a = accounts.current(username);
    if (!a.requiresMfa()) throw new DomainException(ErrorCode.ACCESS_DENIED);
    rates.check("mfa-confirm:" + a.id(), 10, 900);
    mfa.confirm(a.id(), dto.otp());
    session.removeAttribute("mfaEnrollmentAt");
    session.removeAttribute("mfaEnrollmentUser");
    signIn(a, req, res);
    return AccountMapper.view(a);
  }

  @PostMapping("/logout")
  public void logout(HttpServletRequest req, HttpServletResponse res) {
    var session = req.getSession(false);
    if (session != null) session.invalidate();
    SecurityContextHolder.clearContext();
    new HttpSessionCsrfTokenRepository().saveToken(null, req, res);
  }

  private void signIn(Account a, HttpServletRequest req, HttpServletResponse res) {
    req.getSession();
    req.changeSessionId();
    req.getSession().setAttribute("authenticatedAt", System.currentTimeMillis());
    req.getSession().setAttribute("mfaVerified", a.requiresMfa());
    var context = SecurityContextHolder.createEmptyContext();
    var authorities = new ArrayList<SimpleGrantedAuthority>();
    authorities.add(new SimpleGrantedAuthority("ROLE_" + a.role()));
    if (a.organizationMember()) authorities.add(new SimpleGrantedAuthority("ORGANIZATION_MEMBER"));
    context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(a.username(), null, authorities));
    SecurityContextHolder.setContext(context);
    new HttpSessionSecurityContextRepository().saveContext(context, req, res);
    rotateCsrf(req, res);
  }

  private void rotateCsrf(HttpServletRequest req, HttpServletResponse res) {
    // 인증 직후 병렬 조회가 세션 토큰을 중복 생성하지 않도록 먼저 저장한다.
    var repository = new HttpSessionCsrfTokenRepository();
    repository.saveToken(repository.generateToken(req), req, res);
  }
}
