package io.waterleague.common.security;

import io.waterleague.common.exception.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.LinkedHashMap;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.*;
import org.springframework.security.web.SecurityFilterChain;
import tools.jackson.databind.ObjectMapper;

@org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession
@Configuration
public class SecurityConfiguration {
  @Bean
  @org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication
  SecurityFilterChain security(
      HttpSecurity http,
      ObjectMapper json,
      io.waterleague.account.repository.AccountRepository accounts)
      throws Exception {
    return http.addFilterAfter(
            new SessionPolicyFilter(accounts),
            org.springframework.security.web.context.SecurityContextHolderFilter.class)
        .addFilterBefore(
            new RequestSizeFilter(json), org.springframework.security.web.csrf.CsrfFilter.class)
        .csrf(Customizer.withDefaults())
        .cors(cors -> cors.disable())
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .logout(logout -> logout.disable())
        .requestCache(cache -> cache.disable())
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers(
                        HttpMethod.GET, "/api/v1/leagues/joined", "/api/v1/leagues/participations")
                    .hasRole("MEMBER")
                    .requestMatchers(
                        HttpMethod.GET,
                        "/api/v1/health",
                        "/api/v1/competitions",
                        "/api/v1/competitions/catalog",
                        "/api/v1/competitions/{id}",
                        "/api/v1/catalog",
                        "/api/v1/districts",
                        "/api/v1/spatial/play",
                        "/api/v1/spatial/play/forcings",
                        "/api/v1/spatial/play/forcings/{modelHash}",
                        "/api/v1/spatial/play/sites",
                        "/api/v1/spatial/play/sites/{districtId}/{candidateId}",
                        "/api/v1/disasters",
                        "/api/v1/guest-historical",
                        "/api/v1/guest-historical/{id}",
                        "/api/v1/installations",
                        "/api/v1/installations/sites",
                        "/api/v1/installations/sites/ground",
                        "/api/v1/installations/sites/{districtId}/{cellId}",
                        "/api/v1/installations/{id}/physics",
                        "/api/v1/installations/{id}/cost",
                        "/api/v1/rainfall/live",
                        "/api/v1/urban/live",
                        "/api/v1/maps",
                        "/api/v1/lab",
                        "/api/v1/lab/catalog",
                        "/api/v1/leaderboard",
                        "/api/v1/weekly",
                        "/api/v1/surface/current",
                        "/api/v1/surface/current/{id}/frame",
                        "/api/v1/weekly/sites/*/*",
                        "/api/v1/budget",
                        "/api/v1/facilities/epa-designs-v1",
                        "/api/v1/facilities/epa-designs-v2",
                        "/api/v1/facilities/epa-designs-v3",
                        "/api/v1/facilities/epa-designs-v4",
                        "/api/v1/facilities/epa-designs-v5",
                        "/api/v1/facilities/cistern-specifications-v1",
                        "/api/v1/infrastructure/seoul-native-infrastructure-20261020-v1",
                        "/api/v1/infrastructure/equipment-history-20261018-v1",
                        "/api/v1/flood-traces/seoul-flood-traces-20261018-v1/**",
                        "/api/v1/leagues",
                        "/api/v1/leagues/{id}",
                        "/api/v1/organizations",
                        "/api/v1/auth/csrf",
                        "/actuator/health",
                        "/actuator/health/readiness",
                        "/actuator/health/liveness")
                    .permitAll()
                    .requestMatchers(
                        HttpMethod.POST,
                        "/api/v1/guest-historical",
                        "/api/v1/auth/register",
                        "/api/v1/auth/login",
                        "/api/v1/auth/mfa/enrollment",
                        "/api/v1/auth/mfa/confirm")
                    .permitAll()
                    .requestMatchers("/api/v1/competitions/**", "/api/v1/competitions")
                    .authenticated()
                    .requestMatchers("/api/v1/research/**", "/api/v1/institution/**")
                    .hasAuthority("ORGANIZATION_MEMBER")
                    .requestMatchers("/api/v1/admin/**")
                    .hasRole("ADMIN")
                    .requestMatchers("/api/v1/auth/**")
                    .authenticated()
                    .requestMatchers(
                        "/api/v1/strategies/**",
                        "/api/v1/installations/**",
                        "/api/v1/simulations/**",
                        "/api/v1/historical/**",
                        "/api/v1/watersheds/**",
                        "/api/v1/budget/ledger",
                        "/api/v1/comparisons/**",
                        "/api/v1/utilization/**",
                        "/api/v1/submissions",
                        "/api/v1/consents/**",
                        "/api/v1/leagues/**")
                    .hasRole("MEMBER")
                    .requestMatchers(HttpMethod.GET, "/api/v1/spatial/buildings")
                    .authenticated()
                    .anyRequest()
                    .denyAll())
        .exceptionHandling(
            errors ->
                errors
                    .authenticationEntryPoint(
                        (request, response, error) ->
                            write(json, request, response, ErrorCode.AUTHENTICATION_REQUIRED))
                    .accessDeniedHandler(
                        (request, response, error) ->
                            write(json, request, response, ErrorCode.ACCESS_DENIED)))
        .headers(
            headers ->
                headers
                    .contentSecurityPolicy(
                        csp ->
                            csp.policyDirectives(
                                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"))
                    .frameOptions(frame -> frame.deny())
                    .referrerPolicy(
                        ref ->
                            ref.policy(
                                org.springframework.security.web.header.writers
                                    .ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER)))
        .build();
  }

  @Bean
  org.springframework.security.crypto.password.PasswordEncoder encoder() {
    return new org.springframework.security.crypto.argon2.Argon2PasswordEncoder(
        16, 32, 1, 19456, 2);
  }

  @Bean
  UserDetailsService users() {
    // 회원 저장소 연결 전 기본 계정 생성과 인증 우회를 차단한다.
    return username -> {
      throw new UsernameNotFoundException("인증 정보 없음");
    };
  }

  private void write(
      ObjectMapper json, HttpServletRequest request, HttpServletResponse response, ErrorCode code)
      throws IOException {
    var problem = ProblemFactory.create(code, request);
    var body = new LinkedHashMap<String, Object>();
    body.put("type", problem.getType().toString());
    body.put("title", problem.getTitle());
    body.put("status", problem.getStatus());
    body.put("detail", problem.getDetail());
    body.putAll(problem.getProperties());
    response.setStatus(code.status().value());
    response.setContentType("application/problem+json");
    response.setCharacterEncoding("UTF-8");
    json.writeValue(response.getWriter(), body);
  }
}
