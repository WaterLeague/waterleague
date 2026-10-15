package io.waterleague.common.security;

import io.waterleague.common.exception.*;
import org.springframework.context.annotation.*;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;
import org.springframework.security.core.userdetails.*;
import org.springframework.http.HttpMethod;
import tools.jackson.databind.ObjectMapper;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.LinkedHashMap;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain security(HttpSecurity http, ObjectMapper json) throws Exception {
        return http
            .csrf(Customizer.withDefaults())
            .cors(cors -> cors.disable())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .logout(logout -> logout.disable())
            .requestCache(cache -> cache.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/v1/catalog", "/api/v1/maps", "/actuator/health").permitAll()
                .anyRequest().denyAll())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, error) -> write(json, request, response, ErrorCode.AUTHENTICATION_REQUIRED))
                .accessDeniedHandler((request, response, error) -> write(json, request, response, ErrorCode.ACCESS_DENIED)))
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives("default-src 'none'; frame-ancestors 'none'; base-uri 'none'"))
                .frameOptions(frame -> frame.deny())
                .referrerPolicy(ref -> ref.policy(org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER)))
            .build();
    }
    @Bean
    UserDetailsService users() {
        // 회원 저장소 연결 전 기본 계정 생성과 인증 우회를 차단한다.
        return username -> { throw new UsernameNotFoundException("인증 정보 없음"); };
    }
    private void write(ObjectMapper json, HttpServletRequest request, HttpServletResponse response, ErrorCode code) throws IOException {
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
