package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.InstitutionMfaService;
import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class AdminOnlyMfaTests extends PostgresIntegrationTest {
  @Value("${local.server.port}")
  int port;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired InstitutionMfaService mfa;
  HttpClient client =
      HttpClient.newBuilder()
          .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
          .build();

  @BeforeEach
  void reset() {
    db.execute("TRUNCATE accounts, organizations, spring_session, rate_limits CASCADE");
  }

  Account create(String role, String type) {
    UUID id = UUID.randomUUID();
    UUID organization = null;
    if (role.equals("MEMBER") && !type.equals("PLAYER")) {
      organization = UUID.randomUUID();
      db.update(
          "INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", organization, "승인 시험 조직");
    }
    var account =
        new Account(
            id,
            "otp_" + id.toString().substring(0, 8),
            "인증 시험",
            passwords.encode("Test8pw!"),
            role,
            type,
            "APPROVED",
            organization,
            "",
            "",
            true);
    accounts.add(account);
    return account;
  }

  Map<String, String> credentials(Account account) {
    return Map.of("username", account.username(), "password", "Test8pw!");
  }

  HttpResponse<String> call(String path, Object body) throws Exception {
    var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path));
    if (body != null) {
      String token = json.readTree(call("/auth/csrf", null).body()).path("token").asString();
      request
          .header("X-CSRF-TOKEN", token)
          .header("Content-Type", "application/json")
          .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
    }
    return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
  }

  @Test
  void everyMemberTypeUsesPasswordAndCannotEnrollOtp() throws Exception {
    for (String type : List.of("PLAYER", "BUSINESS", "INSTITUTION", "GOVERNMENT")) {
      var member = create("MEMBER", type);
      assertThat(member.requiresMfa()).isFalse();
      assertThat(call("/auth/login", credentials(member)).statusCode()).isEqualTo(200);
      assertThat(call("/auth/mfa/enrollment", credentials(member)).statusCode()).isEqualTo(403);
      assertThat(call("/admin/members", null).statusCode()).isEqualTo(403);
      // 이전 등록 기록이 남은 계정도 인증 앱 번호 없이 로그인한다.
      mfa.provision(member.id());
      assertThat(call("/auth/login", credentials(member)).statusCode()).isEqualTo(200);
      db.update("UPDATE accounts SET approval_status='SUSPENDED' WHERE id=?", member.id());
      assertThat(call("/auth/me", null).statusCode()).isEqualTo(401);
      assertThat(call("/auth/login", credentials(member)).statusCode()).isEqualTo(403);
    }
  }

  @Test
  void administratorEnrollmentChallengeReplayAndSessionRemainProtected() throws Exception {
    var admin = create("ADMIN", null);
    assertThat(
            call("/auth/login", Map.of("username", admin.username(), "password", "wrong-password"))
                .body())
        .doesNotContain("MFA_");
    assertThat(call("/auth/login", credentials(admin)).body()).contains("MFA_ENROLLMENT_REQUIRED");
    var enrollment = call("/auth/mfa/enrollment", credentials(admin));
    assertThat(enrollment.statusCode()).isEqualTo(200);
    String secret = json.readTree(enrollment.body()).path("secret").asString();
    assertThat(call("/auth/me", null).statusCode()).isEqualTo(401);
    String otp = MfaTests.otp(secret);
    assertThat(call("/auth/mfa/confirm", Map.of("otp", otp)).statusCode()).isEqualTo(200);
    assertThat(call("/admin/members", null).statusCode()).isEqualTo(200);
    db.update("DELETE FROM spring_session_attributes WHERE attribute_name='mfaVerified'");
    assertThat(call("/admin/members", null).statusCode()).isEqualTo(401);
    var challenge = call("/auth/login", credentials(admin));
    assertThat(challenge.statusCode()).isEqualTo(403);
    assertThat(challenge.body()).contains("MFA_REQUIRED");
    assertThat(call("/auth/me", null).statusCode()).isEqualTo(401);
    assertThat(
            call(
                    "/auth/login",
                    Map.of("username", admin.username(), "password", "Test8pw!", "otp", otp))
                .statusCode())
        .isEqualTo(401);
  }

  @Test
  void migrationRemovesOnlyMemberSecretsAndPreservesAdministrator() throws Exception {
    var admin = create("ADMIN", null);
    var member = create("MEMBER", "INSTITUTION");
    mfa.provision(admin.id());
    mfa.provision(member.id());
    String original =
        db.queryForObject(
            "SELECT encrypted_secret FROM account_mfa WHERE account_id=?",
            String.class,
            admin.id());
    try (var input =
        new ClassPathResource("db/migration/V35__admin_only_mfa.sql").getInputStream()) {
      db.execute(new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
    }
    assertThat(db.queryForObject("SELECT count(*) FROM account_mfa", Integer.class)).isEqualTo(1);
    assertThat(
            db.queryForObject(
                "SELECT encrypted_secret FROM account_mfa WHERE account_id=?",
                String.class,
                admin.id()))
        .isEqualTo(original);
  }
}
