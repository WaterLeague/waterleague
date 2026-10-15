package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.model.service.LabModelService;
import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class ResearchWorkflowTests {
  @Value("${local.server.port}")
  int port;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired LabModelService model;
  @Autowired io.waterleague.account.service.InstitutionMfaService mfa;

  record Actor(UUID id, HttpClient client) {}

  Actor actor(UUID org) throws Exception {
    UUID id = UUID.randomUUID();
    String name = "qa_" + id.toString().substring(0, 8);
    accounts.add(
        new Account(
            id,
            name,
            name,
            passwords.encode("test-password-1234"),
            org == null ? "PLAYER" : "INSTITUTION",
            org,
            true));
    String secret = org == null ? null : mfa.provision(id);
    var a =
        new Actor(
            id,
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    var login = new HashMap<String, Object>();
    login.put("username", name);
    login.put("password", "test-password-1234");
    if (secret != null) login.put("otp", MfaTests.otp(secret));
    assertThat(call(a, "POST", "/auth/login", login).statusCode()).isEqualTo(200);
    return a;
  }

  HttpResponse<String> call(Actor a, String method, String path, Object body) throws Exception {
    var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path));
    if (!method.equals("GET")) {
      var csrf =
          a.client()
              .send(
                  HttpRequest.newBuilder(
                          URI.create("http://127.0.0.1:" + port + "/api/v1/auth/csrf"))
                      .build(),
                  HttpResponse.BodyHandlers.ofString());
      builder
          .header("X-CSRF-TOKEN", json.readTree(csrf.body()).get("token").asString())
          .header("Content-Type", "application/json")
          .method(method, HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
    }
    return a.client().send(builder.build(), HttpResponse.BodyHandlers.ofString());
  }

  JsonNode ok(Actor a, String method, String path, Object body, int status) throws Exception {
    var r = call(a, method, path, body);
    assertThat(r.statusCode()).as(r.body()).isEqualTo(status);
    return json.readTree(r.body());
  }

  Map<String, Object> draft(int revision, String note) {
    return Map.of(
        "title",
        "검증 설계",
        "modelHash",
        model.hash(),
        "placements",
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 40)),
        "designNote",
        note,
        "baseRevision",
        revision);
  }

  JsonNode create(Actor a) throws Exception {
    return ok(a, "POST", "/strategies", draft(0, "제출 이전 메모"), 200);
  }

  @Test
  void protectsOwnershipAndImmutableRevisionAndServerBudget() throws Exception {
    var owner = actor(null);
    var other = actor(null);
    var v = create(owner);
    String id = v.get("strategyId").asString();
    assertThat(v.get("cost").decimalValue()).isEqualByComparingTo("22400000");
    assertThat(call(other, "GET", "/strategies/" + id, null).statusCode()).isEqualTo(404);
    assertThat(call(other, "POST", "/strategies/" + id + "/versions", draft(1, "침입")).statusCode())
        .isEqualTo(404);
    assertThat(call(owner, "POST", "/strategies/" + id + "/versions", draft(0, "충돌")).statusCode())
        .isEqualTo(409);
    ok(owner, "POST", "/strategies/" + id + "/versions", draft(1, "새 메모"), 200);
    var history = ok(owner, "GET", "/strategies/" + id, null, 200).get("versions");
    assertThat(history.size()).isEqualTo(2);
    assertThat(history.get(0).get("designNote").asString()).isEqualTo("제출 이전 메모");
    var invalid = new HashMap<>(draft(0, ""));
    invalid.put(
        "placements", List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 81)));
    assertThat(call(owner, "POST", "/strategies", invalid).statusCode()).isEqualTo(422);
    invalid = new HashMap<>(draft(0, ""));
    invalid.put("cost", 1);
    assertThat(call(owner, "POST", "/strategies", invalid).statusCode()).isEqualTo(400);
  }

  @Test
  void enforcesQueueIdempotencyAndOwnerLimit() throws Exception {
    var a = actor(null);
    var b = actor(null);
    var v = create(a);
    var key = UUID.randomUUID();
    var body = Map.of("versionId", v.get("id").asString(), "requestKey", key);
    var job = ok(a, "POST", "/simulations", body, 202);
    assertThat(ok(a, "POST", "/simulations", body, 202).get("id")).isEqualTo(job.get("id"));
    assertThat(call(b, "GET", "/simulations/" + job.get("id").asString(), null).statusCode())
        .isEqualTo(404);
    assertThat(call(b, "POST", "/simulations", body).statusCode()).isEqualTo(404);
    var v2 = create(a);
    assertThat(
            call(
                    a,
                    "POST",
                    "/simulations",
                    Map.of("versionId", v2.get("id").asString(), "requestKey", key))
                .statusCode())
        .isEqualTo(409);
    for (int i = 0; i < 2; i++)
      ok(
          a,
          "POST",
          "/simulations",
          Map.of("versionId", v.get("id").asString(), "requestKey", UUID.randomUUID()),
          202);
    assertThat(
            call(
                    a,
                    "POST",
                    "/simulations",
                    Map.of("versionId", v.get("id").asString(), "requestKey", UUID.randomUUID()))
                .statusCode())
        .isEqualTo(429);
  }

  @Test
  void recomputesScoreAndRestrictsInstitutionAndRevocation() throws Exception {
    UUID orgA = UUID.randomUUID(), orgB = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", orgA, "시험 기관 A");
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", orgB, "시험 기관 B");
    var player = actor(null);
    var a = actor(orgA);
    var b = actor(orgB);
    var v = create(player);
    var job =
        ok(
            player,
            "POST",
            "/simulations",
            Map.of("versionId", v.get("id").asString(), "requestKey", UUID.randomUUID()),
            202);
    UUID id = UUID.fromString(job.get("id").asString());
    assertThat(call(player, "POST", "/submissions", Map.of("jobId", id)).statusCode())
        .isEqualTo(409);
    // 워커 결과 시험 고정값. 현장 관측·실제 SWMM 결과로 공개하지 않는다.
    var result =
        Map.of(
            "modelHash",
            model.hash(),
            "inputHash",
            v.get("inputHash").asString(),
            "validationLevel",
            "EXPLORATORY",
            "official",
            false,
            "score",
            9999,
            "baseline",
            Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 100),
            "strategy",
            Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 90));
    db.update(
        "UPDATE simulation_jobs SET state='SUCCEEDED',result=? WHERE id=?",
        json.writeValueAsString(result),
        id);
    assertThat(
            ok(player, "POST", "/submissions", Map.of("jobId", id), 200)
                .get("score")
                .decimalValue())
        .isEqualByComparingTo("10");
    assertThat(call(a, "GET", "/research/strategies/" + id, null).statusCode()).isEqualTo(404);
    assertThat(call(player, "PUT", "/consents/" + orgA, Map.of("granted", true)).statusCode())
        .isEqualTo(200);
    ok(
        player,
        "POST",
        "/strategies/" + v.get("strategyId").asString() + "/versions",
        draft(1, "미제출 비공개 후속 메모"),
        200);
    var details = ok(a, "GET", "/research/strategies/" + id, null, 200);
    assertThat(details.get("history").size()).isEqualTo(1);
    assertThat(details.toString()).doesNotContain("미제출 비공개 후속 메모", "passwordHash", "username");
    assertThat(call(b, "GET", "/research/strategies/" + id, null).statusCode()).isEqualTo(404);
    assertThat(call(player, "PUT", "/consents/" + orgA, Map.of("granted", false)).statusCode())
        .isEqualTo(200);
    assertThat(call(a, "GET", "/research/strategies/" + id, null).statusCode()).isEqualTo(404);
    assertThat(call(a, "GET", "/research/strategies/" + id + "/bundle", null).statusCode())
        .isEqualTo(404);
    db.update("UPDATE accounts SET enabled=false WHERE id=?", a.id());
    assertThat(call(a, "GET", "/research/strategies", null).statusCode()).isEqualTo(401);
  }

  @Test
  void requiresInstitutionMfaRejectsReplayAndCapsBody() throws Exception {
    UUID org = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", org, "MFA 시험 기관");
    var a = actor(org);
    String name =
        db.queryForObject("SELECT username FROM accounts WHERE id=?", String.class, a.id());
    var login = new HashMap<String, Object>();
    login.put("username", name);
    login.put("password", "test-password-1234");
    assertThat(call(a, "POST", "/auth/login", login).statusCode()).isEqualTo(401);
    String secret = mfa.provision(a.id());
    String code = MfaTests.otp(secret);
    login.put("otp", code);
    assertThat(call(a, "POST", "/auth/login", login).statusCode()).isEqualTo(200);
    assertThat(call(a, "POST", "/auth/login", login).statusCode()).isEqualTo(401);
    assertThat(call(a, "POST", "/strategies", Map.of("title", "x".repeat(70000))).statusCode())
        .isEqualTo(413);
    var encrypted =
        db.queryForObject(
            "SELECT encrypted_secret FROM account_mfa WHERE account_id=?", String.class, a.id());
    assertThat(encrypted).doesNotContain(secret);
    var other = actor(org);
    db.update(
        "UPDATE account_mfa SET encrypted_secret=? WHERE account_id=?", encrypted, other.id());
    assertThatThrownBy(() -> mfa.verify(other.id(), code))
        .isInstanceOf(io.waterleague.common.exception.DomainException.class);
  }
}
