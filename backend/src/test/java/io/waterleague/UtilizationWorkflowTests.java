package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.InstitutionMfaService;
import io.waterleague.model.service.LabModelService;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.zip.ZipInputStream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties =
        "spring.datasource.url=jdbc:h2:mem:utilization;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@ActiveProfiles("local")
class UtilizationWorkflowTests {
  @Value("${local.server.port}")
  int port;

  @Value("${waterleague.artifacts}")
  String artifacts;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired InstitutionMfaService mfa;
  @Autowired LabModelService model;

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
            "MEMBER",
            org == null ? "PLAYER" : "INSTITUTION",
            "APPROVED",
            org,
            "",
            "",
            true));
    var actor =
        new Actor(
            id,
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    var input = new HashMap<String, Object>();
    input.put("username", name);
    input.put("password", "test-password-1234");
    if (org != null) input.put("otp", MfaTests.otp(mfa.provision(id)));
    ok(actor, "POST", "/auth/login", input, 200);
    return actor;
  }

  UUID organization() {
    var id = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", id, "활용 검토 시험 조직");
    return id;
  }

  HttpResponse<byte[]> call(Actor a, String method, String path, Object body) throws Exception {
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
    return a.client().send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
  }

  JsonNode ok(Actor a, String method, String path, Object body, int code) throws Exception {
    var response = call(a, method, path, body);
    assertThat(response.statusCode()).as(new String(response.body())).isEqualTo(code);
    return json.readTree(response.body());
  }

  UUID submitted(Actor owner) throws Exception {
    var version =
        ok(
            owner,
            "POST",
            "/strategies",
            Map.of(
                "title",
                "활용 동의 시험",
                "modelHash",
                LegacyModelFixtures.HASH,
                "placements",
                List.of(),
                "designNote",
                "",
                "baseRevision",
                0),
            200);
    var job =
        ok(
            owner,
            "POST",
            "/simulations",
            Map.of("versionId", version.get("id").asString(), "requestKey", UUID.randomUUID()),
            202);
    UUID id = UUID.fromString(job.get("id").asString());
    // 접근 제어 검사 전용 결과이며 현장 관측·운영 계산이 아님.
    var result =
        Map.of(
            "modelHash",
            LegacyModelFixtures.HASH,
            "inputHash",
            version.get("inputHash").asString(),
            "validationLevel",
            "EXPLORATORY",
            "official",
            false,
            "baseline",
            Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 100),
            "strategy",
            Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 90),
            "artifactToken",
            UUID.randomUUID());
    db.update(
        "UPDATE simulation_jobs SET state='SUCCEEDED',result=? WHERE id=?",
        json.writeValueAsString(result),
        id);
    ok(owner, "POST", "/submissions", Map.of("jobId", id), 200);
    return id;
  }

  Map<String, Object> request(UUID job, UUID key) {
    return Map.of(
        "jobId",
        job,
        "requestKey",
        key,
        "title",
        "성수 후보 배치 검토",
        "purpose",
        "현장 배수 자료와 시설 설치 가능성을 비교하는 예비 검토");
  }

  Map<String, Object> decision(JsonNode r, String action) {
    return Map.of(
        "expectedRevision",
        r.get("revision").asInt(),
        "termsHash",
        r.get("termsHash").asString(),
        "decision",
        action);
  }

  void consent(Actor owner, UUID org, boolean value) throws Exception {
    assertThat(call(owner, "PUT", "/consents/" + org, Map.of("granted", value)).statusCode())
        .isEqualTo(200);
  }

  @Test
  void separatesResearchAndApplicationPermissionAndProtectsFrozenScope() throws Exception {
    var owner = actor(null);
    var other = actor(null);
    UUID org = organization();
    var institution = actor(org);
    var stranger = actor(organization());
    UUID job = submitted(owner), key = UUID.randomUUID();
    assertThat(
            call(institution, "POST", "/institution/utilization/requests", request(job, key))
                .statusCode())
        .isEqualTo(404);
    consent(owner, org, true);
    var r = ok(institution, "POST", "/institution/utilization/requests", request(job, key), 201);
    String id = r.get("id").asString();
    assertThat(r.toString()).doesNotContain("ownerId", "requestedBy", "username");
    assertThat(
            ok(institution, "POST", "/institution/utilization/requests", request(job, key), 201)
                .get("id"))
        .isEqualTo(r.get("id"));
    assertThat(
            call(
                    institution,
                    "POST",
                    "/institution/utilization/requests",
                    request(job, UUID.randomUUID()))
                .statusCode())
        .isEqualTo(409);
    var changed = new HashMap<>(request(job, key));
    changed.put("purpose", "변경된 현장 활용 목적에 대한 별도 검토");
    assertThat(call(institution, "POST", "/institution/utilization/requests", changed).statusCode())
        .isEqualTo(409);
    assertThat(call(other, "GET", "/utilization/requests/" + id, null).statusCode()).isEqualTo(404);
    assertThat(call(stranger, "GET", "/utilization/requests/" + id, null).statusCode())
        .isEqualTo(404);
    assertThat(
            call(
                    institution,
                    "POST",
                    "/utilization/requests/" + id + "/decisions",
                    decision(r, "GRANT"))
                .statusCode())
        .isEqualTo(404);
    String bundle = "/institution/utilization/requests/" + id + "/bundle";
    assertThat(call(institution, "GET", bundle, null).statusCode()).isEqualTo(404);
    var stale = new HashMap<>(decision(r, "GRANT"));
    stale.put("termsHash", "0".repeat(64));
    assertThat(
            call(owner, "POST", "/utilization/requests/" + id + "/decisions", stale).statusCode())
        .isEqualTo(409);
    var granted =
        ok(owner, "POST", "/utilization/requests/" + id + "/decisions", decision(r, "GRANT"), 200);
    assertThat(granted.get("state").asString()).isEqualTo("GRANTED");
    assertThat(
            call(owner, "POST", "/utilization/requests/" + id + "/decisions", decision(r, "GRANT"))
                .statusCode())
        .isEqualTo(409);
    consent(owner, org, false);
    assertThat(call(institution, "GET", "/research/strategies/" + job, null).statusCode())
        .isEqualTo(404);
    var token =
        json.readTree(
                db.queryForObject(
                    "SELECT result FROM simulation_jobs WHERE id=?", String.class, job))
            .get("artifactToken")
            .asString();
    Path dir = Path.of(artifacts, job.toString(), token);
    Files.createDirectories(dir);
    var names =
        List.of(
            "manifest.json",
            "builder.py",
            "model-source.json",
            "model.json",
            "placements.json",
            "request.json",
            "result.json",
            "baseline.inp",
            "baseline.rpt",
            "baseline.out",
            "strategy.inp",
            "strategy.rpt",
            "strategy.out",
            "low.inp",
            "low.rpt",
            "low.out",
            "high.inp",
            "high.rpt",
            "high.out");
    try {
      for (var name : names) Files.writeString(dir.resolve(name), "{}");
      var exported = call(institution, "GET", bundle, null);
      assertThat(exported.statusCode()).isEqualTo(200);
      JsonNode scope = null;
      try (var zip = new ZipInputStream(new java.io.ByteArrayInputStream(exported.body()))) {
        java.util.zip.ZipEntry entry;
        while ((entry = zip.getNextEntry()) != null)
          if (entry.getName().equals("access-scope.json"))
            scope = json.readTree(zip.readAllBytes());
      }
      assertThat(scope).isNotNull();
      assertThat(scope.get("purpose").asString()).isEqualTo("APPLICATION_REVIEW");
      assertThat(scope.get("jobId").asString()).isEqualTo(job.toString());
      assertThat(scope.get("termsHash")).isEqualTo(r.get("termsHash"));
      assertThat(scope.get("consentRevision").asInt()).isEqualTo(2);
      assertThat(call(stranger, "GET", bundle, null).statusCode()).isEqualTo(404);
      db.update("UPDATE accounts SET enabled=false WHERE id=?", owner.id());
      assertThat(call(institution, "GET", bundle, null).statusCode()).isEqualTo(404);
      db.update("UPDATE accounts SET enabled=true WHERE id=?", owner.id());
      db.update("UPDATE organizations SET approved=false WHERE id=?", org);
      assertThat(call(institution, "GET", bundle, null).statusCode()).isEqualTo(403);
      db.update("UPDATE organizations SET approved=true WHERE id=?", org);
      // 정지 상태를 읽은 소유자 세션은 사용하지 않았으므로 기존 세션 유지.
      var revoked =
          ok(
              owner,
              "POST",
              "/utilization/requests/" + id + "/decisions",
              decision(granted, "REVOKE"),
              200);
      assertThat(revoked.get("state").asString()).isEqualTo("REVOKED");
      consent(owner, org, true);
      assertThat(call(institution, "GET", "/research/strategies/" + job, null).statusCode())
          .isEqualTo(200);
      assertThat(call(institution, "GET", bundle, null).statusCode()).isEqualTo(404);
      assertThat(ok(owner, "GET", "/utilization/requests/" + id, null, 200).get("decisions").size())
          .isEqualTo(2);
    } finally {
      for (var name : names) Files.deleteIfExists(dir.resolve(name));
      Files.deleteIfExists(dir);
      Files.deleteIfExists(dir.getParent());
    }
  }

  @Test
  void recordsAppendOnlyReviewsAndRetainsOwnerVisibilityAfterWithdrawal() throws Exception {
    var owner = actor(null);
    UUID org = organization();
    var institution = actor(org);
    var other = actor(organization());
    UUID job = submitted(owner);
    var payload =
        Map.of(
            "state", "NEEDS_EVIDENCE", "reason", "유출 관측과의 대조 필요", "limitations", "관로 표고·단면 자료 미확보");
    String url = "/research/strategies/" + job + "/reviews";
    assertThat(call(institution, "POST", url, payload).statusCode()).isEqualTo(404);
    consent(owner, org, true);
    var first = ok(institution, "POST", url, payload, 201);
    ok(
        institution,
        "POST",
        url,
        Map.of("state", "CANDIDATE", "reason", "추가 비교 대상에 포함", "limitations", "현장 검증 전 상태 유지"),
        201);
    assertThat(ok(institution, "GET", url, null, 200).get("items").size()).isEqualTo(2);
    assertThat(call(other, "GET", url, null).statusCode()).isEqualTo(404);
    var bad = new HashMap<>(payload);
    bad.put("state", "APPLIED");
    assertThat(call(institution, "POST", url, bad).statusCode()).isEqualTo(400);
    consent(owner, org, false);
    assertThat(call(institution, "GET", url, null).statusCode()).isEqualTo(404);
    var seen = ok(owner, "GET", "/utilization/reviews", null, 200).get("items");
    assertThat(seen.size()).isEqualTo(2);
    assertThat(seen.toString())
        .contains(first.get("reason").asString())
        .doesNotContain("reviewerId", "username");
  }

  @Test
  void serializesConcurrentRequestsAndDecisionsAndRollsBackFailedEvents() throws Exception {
    var owner = actor(null);
    UUID org = organization();
    var institution = actor(org);
    UUID job = submitted(owner);
    consent(owner, org, true);
    try (var executor = Executors.newFixedThreadPool(2)) {
      var gate = new CountDownLatch(1);
      var tasks = new ArrayList<Future<HttpResponse<byte[]>>>();
      for (int i = 0; i < 2; i++)
        tasks.add(
            executor.submit(
                () -> {
                  gate.await();
                  return call(
                      institution,
                      "POST",
                      "/institution/utilization/requests",
                      request(job, UUID.randomUUID()));
                }));
      gate.countDown();
      var responses = List.of(tasks.get(0).get(), tasks.get(1).get());
      assertThat(responses.stream().map(HttpResponse::statusCode).sorted().toList())
          .containsExactly(201, 409);
      var r =
          json.readTree(
              responses.stream()
                  .filter(v -> v.statusCode() == 201)
                  .findFirst()
                  .orElseThrow()
                  .body());
      String id = r.get("id").asString();
      db.execute(
          "ALTER TABLE utilization_decisions ADD CONSTRAINT test_event_failure CHECK(request_id <>"
              + " '"
              + id
              + "')");
      try {
        assertThat(
                call(
                        owner,
                        "POST",
                        "/utilization/requests/" + id + "/decisions",
                        decision(r, "GRANT"))
                    .statusCode())
            .isEqualTo(500);
      } finally {
        db.execute("ALTER TABLE utilization_decisions DROP CONSTRAINT test_event_failure");
      }
      assertThat(
              ok(owner, "GET", "/utilization/requests/" + id, null, 200)
                  .get("request")
                  .get("state")
                  .asString())
          .isEqualTo("PENDING");
      var decisions = new ArrayList<Future<HttpResponse<byte[]>>>();
      var gate2 = new CountDownLatch(1);
      for (var action : List.of("GRANT", "DECLINE"))
        decisions.add(
            executor.submit(
                () -> {
                  gate2.await();
                  return call(
                      owner,
                      "POST",
                      "/utilization/requests/" + id + "/decisions",
                      decision(r, action));
                }));
      gate2.countDown();
      assertThat(
              List.of(decisions.get(0).get().statusCode(), decisions.get(1).get().statusCode())
                  .stream()
                  .sorted()
                  .toList())
          .containsExactly(200, 409);
      assertThat(ok(owner, "GET", "/utilization/requests/" + id, null, 200).get("decisions").size())
          .isEqualTo(1);
    }
  }

  @Test
  void paginatesEqualTimestampsWithoutForeignCursors() throws Exception {
    var owner = actor(null);
    var foreign = actor(null);
    UUID org = organization();
    var institution = actor(org);
    UUID job = submitted(owner);
    consent(owner, org, true);
    var r =
        ok(
            institution,
            "POST",
            "/institution/utilization/requests",
            request(job, UUID.randomUUID()),
            201);
    UUID original = UUID.fromString(r.get("id").asString());
    var same = java.sql.Timestamp.from(Instant.parse("2026-01-01T00:00:00Z"));
    db.update("UPDATE utilization_requests SET created_at=? WHERE id=?", same, original);
    for (int i = 0; i < 52; i++)
      db.update(
          "INSERT INTO utilization_requests SELECT"
              + " ?,job_id,version_id,model_hash,owner_id,organization_id,requested_by,?,title,purpose,policy_version,terms_hash,'DECLINED',1,created_at,updated_at"
              + " FROM utilization_requests WHERE id=?",
          UUID.randomUUID(),
          UUID.randomUUID(),
          original);
    var first = ok(owner, "GET", "/utilization/requests", null, 200);
    assertThat(first.get("items").size()).isEqualTo(50);
    String cursor = first.get("nextCursor").asString();
    var second = ok(owner, "GET", "/utilization/requests?after=" + cursor, null, 200);
    assertThat(second.get("items").size()).isEqualTo(3);
    assertThat(second.get("nextCursor").isNull()).isTrue();
    Set<String> ids = new HashSet<>();
    first.get("items").forEach(v -> ids.add(v.get("id").asString()));
    second.get("items").forEach(v -> ids.add(v.get("id").asString()));
    assertThat(ids).hasSize(53);
    assertThat(call(foreign, "GET", "/utilization/requests?after=" + cursor, null).statusCode())
        .isEqualTo(404);
  }
}
