package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.model.service.LabModelService;
import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties =
        "spring.datasource.url=jdbc:h2:mem:research_analysis;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@ActiveProfiles("local")
class ResearchAnalysisWorkflowTests {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    String url = System.getProperty("waterleague.integration.jdbc");
    if (url != null) {
      registry.add("spring.datasource.url", () -> url);
      registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
      registry.add("spring.datasource.username", () -> System.getenv("WL_INTEGRATION_USER"));
      registry.add("spring.datasource.password", () -> System.getenv("WL_INTEGRATION_PASSWORD"));
    }
  }

  @Value("${local.server.port}")
  int port;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired org.springframework.transaction.PlatformTransactionManager transactions;
  @Autowired io.waterleague.research.repository.ResearchRepository research;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired LabModelService model;
  @Autowired io.waterleague.account.service.InstitutionMfaService mfa;

  @Value("${waterleague.artifacts}")
  String artifactRoot;

  record Actor(UUID id, HttpClient client) {}

  @BeforeEach
  void resetTestRateBuckets() {
    // 각 시나리오의 로그인 시도가 다른 시험의 횟수 제한에 영향을 주지 않도록 분리한다.
    db.update("DELETE FROM rate_limits");
  }

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
        LegacyModelFixtures.HASH,
        "placements",
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 40)),
        "designNote",
        note,
        "baseRevision",
        revision);
  }

  Actor institution() throws Exception {
    UUID org = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", org, "리그 시험 기관");
    return actor(org);
  }

  JsonNode successfulJob(Actor player, int discharge) throws Exception {
    return successfulJob(
        player,
        discharge,
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 40)));
  }

  JsonNode successfulJob(Actor player, int discharge, List<Map<String, Object>> placements)
      throws Exception {
    var body = new HashMap<>(draft(0, "검증 계산"));
    body.put("placements", placements);
    var v = ok(player, "POST", "/strategies", body, 200);
    var j =
        ok(
            player,
            "POST",
            "/simulations",
            Map.of("versionId", v.get("id").asString(), "requestKey", UUID.randomUUID()),
            202);
    var m = (JsonNode) model.view(LegacyModelFixtures.HASH).get("model");
    var result =
        Map.of(
            "modelHash",
            LegacyModelFixtures.HASH,
            "inputHash",
            v.get("inputHash").asString(),
            "validationLevel",
            "EXPLORATORY",
            "official",
            false,
            "baseline",
            Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 100),
            "strategy",
            Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", discharge),
            "engine",
            Map.of(
                "revision",
                m.path("engineRevision").asString(),
                "generatorSha256",
                m.path("generatorSha256").asString(),
                "binarySha256",
                "a".repeat(64)));
    db.update(
        "UPDATE simulation_jobs SET state='SUCCEEDED',result=? WHERE id=?",
        json.writeValueAsString(result),
        UUID.fromString(j.get("id").asString()));
    return j;
  }

  @Autowired io.waterleague.model.repository.LabModelRepository models;

  UUID organization(Actor a) {
    return accounts.byId(a.id()).orElseThrow().organizationId();
  }

  void share(Actor owner, Actor org, boolean granted) throws Exception {
    ok(owner, "PUT", "/consents/" + organization(org), Map.of("granted", granted), 200);
  }

  JsonNode submitted(Actor owner, int discharge, int area) throws Exception {
    var job =
        successfulJob(
            owner,
            discharge,
            List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", area)));
    ok(owner, "POST", "/submissions", Map.of("jobId", job.path("id").asString()), 200);
    return job;
  }

  Map<String, Object> request(JsonNode job, UUID key, int count) {
    return Map.of(
        "sourceJobId",
        job.path("id").asString(),
        "requestKey",
        key,
        "modelHashes",
        models.all().stream().map(m -> m.hash()).limit(count).toList());
  }

  int versions(Actor a) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM strategy_versions v JOIN strategies s ON s.id=v.strategy_id WHERE"
            + " s.owner_id=?",
        Integer.class,
        a.id());
  }

  int active(Actor a) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM simulation_jobs WHERE owner_id=? AND state IN ('QUEUED','RUNNING')",
        Integer.class,
        a.id());
  }

  UUID complete(UUID job, int discharge) throws Exception {
    var row = db.queryForMap("SELECT model_hash,input_hash FROM simulation_jobs WHERE id=?", job);
    UUID token = UUID.randomUUID();
    // 파일/권한 검사 전용 고정값이며 실제 SWMM 수치 검증에 사용하지 않는다.
    db.update(
        "UPDATE simulation_jobs SET state='SUCCEEDED',result=? WHERE id=?",
        json.writeValueAsString(
            Map.of(
                "modelHash",
                row.get("model_hash"),
                "inputHash",
                row.get("input_hash"),
                "validationLevel",
                "EXPLORATORY",
                "official",
                false,
                "score",
                9999,
                "artifactToken",
                token,
                "baseline",
                Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 100),
                "strategy",
                Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", discharge))),
        job);
    return token;
  }

  String path(JsonNode c) {
    return "/research/comparisons/" + c.path("id").asString();
  }

  @Test
  void requiresConsentKeepsSourceOwnershipAndReusesOnlyMatchingOrganizationRequest()
      throws Exception {
    var owner = actor(null);
    var org = institution();
    var other = institution();
    var job = submitted(owner, 90, 40);
    var key = UUID.randomUUID();
    var request = request(job, key, 3);
    assertThat(call(org, "POST", "/research/comparisons", request).statusCode()).isEqualTo(404);
    share(owner, org, true);
    share(owner, other, true);
    var response = call(org, "POST", "/research/comparisons", request);
    assertThat(response.statusCode()).as(response.body()).isEqualTo(202);
    assertThat(response.headers().firstValue("cache-control").orElse("")).contains("no-store");
    var c = json.readTree(response.body());
    assertThat(c.path("comparison").path("jobs").size()).isEqualTo(3);
    assertThat(versions(owner)).isEqualTo(4);
    assertThat(versions(org)).isZero();
    for (var target : c.path("comparison").path("jobs")) {
      var detail =
          ok(owner, "GET", "/strategies/" + target.path("strategyId").asString(), null, 200);
      var v = detail.path("versions").get(0);
      assertThat(v.path("placements"))
          .isEqualTo(c.path("comparison").path("sourceVersion").path("placements"));
      assertThat(v.path("events").path("kind").asString())
          .isEqualTo("RESEARCH_RAINFALL_COMPARISON_COPY");
      assertThat(v.path("events").path("organizationId").asString())
          .isEqualTo(organization(org).toString());
      assertThat(
              call(org, "GET", "/strategies/" + target.path("strategyId").asString(), null)
                  .statusCode())
          .isEqualTo(404);
      assertThat(
              call(org, "GET", "/simulations/" + target.path("id").asString(), null).statusCode())
          .isEqualTo(404);
    }
    var reordered = new HashMap<>(request);
    reordered.put(
        "modelHashes", models.all().stream().map(m -> m.hash()).limit(3).toList().reversed());
    assertThat(ok(org, "POST", "/research/comparisons", reordered, 202).path("id"))
        .isEqualTo(c.path("id"));
    assertThat(versions(owner)).isEqualTo(4);
    assertThat(call(org, "POST", "/research/comparisons", request(job, key, 2)).statusCode())
        .isEqualTo(409);
    assertThat(call(other, "GET", path(c), null).statusCode()).isEqualTo(404);
    assertThat(ok(other, "GET", "/research/comparisons", null, 200)).isEmpty();
    assertThat(call(owner, "GET", path(c), null).statusCode()).isEqualTo(403);
    assertThat(
            call(org, "GET", "/comparisons/" + c.path("comparison").path("id").asString(), null)
                .statusCode())
        .isEqualTo(404);
    var colleague = actor(organization(org));
    ok(colleague, "GET", path(c), null, 200);
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM submissions WHERE owner_id=?", Integer.class, owner.id()))
        .isEqualTo(1);
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM utilization_requests WHERE owner_id=?",
                Integer.class,
                owner.id()))
        .isZero();
    var guest = new Actor(UUID.randomUUID(), HttpClient.newHttpClient());
    assertThat(call(guest, "GET", path(c), null).statusCode()).isEqualTo(401);
    var noCsrf =
        org.client()
            .send(
                HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/api/v1/research/comparisons"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(request)))
                    .build(),
                HttpResponse.BodyHandlers.ofString());
    assertThat(noCsrf.statusCode()).isEqualTo(403);
  }

  @Test
  void rechecksConsentAndOrganizationForDetailListAndScopedBundle() throws Exception {
    var owner = actor(null);
    var org = institution();
    var other = institution();
    var job = submitted(owner, 90, 40);
    share(owner, org, true);
    share(owner, other, true);
    var c = ok(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 2), 202);
    var target = UUID.fromString(c.path("comparison").path("jobs").get(0).path("id").asString());
    UUID token = complete(target, 91);
    var dir = java.nio.file.Path.of(artifactRoot, target.toString(), token.toString());
    java.nio.file.Files.createDirectories(dir);
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
    String bundle = path(c) + "/jobs/" + target + "/bundle";
    try {
      for (String name : names) java.nio.file.Files.writeString(dir.resolve(name), "{}");
      var exported =
          org.client()
              .send(
                  HttpRequest.newBuilder(
                          URI.create("http://127.0.0.1:" + port + "/api/v1" + bundle))
                      .build(),
                  HttpResponse.BodyHandlers.ofByteArray());
      assertThat(exported.statusCode()).isEqualTo(200);
      try (var zip =
          new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(exported.body()))) {
        java.util.zip.ZipEntry entry;
        boolean found = false;
        while ((entry = zip.getNextEntry()) != null)
          if (entry.getName().equals("access-scope.json")) {
            var scope = json.readTree(zip.readAllBytes());
            found = true;
            assertThat(scope.path("purpose").asString()).isEqualTo("RESEARCH_RAINFALL_COMPARISON");
            assertThat(scope.path("sourceJobId")).isEqualTo(job.path("id"));
            assertThat(scope.path("researchComparisonId")).isEqualTo(c.path("id"));
            assertThat(scope.path("requestHash")).isEqualTo(c.path("requestHash"));
          }
        assertThat(found).isTrue();
      }
      assertThat(call(other, "GET", bundle, null).statusCode()).isEqualTo(404);
      assertThat(
              call(org, "GET", path(c) + "/jobs/" + job.path("id").asString() + "/bundle", null)
                  .statusCode())
          .isEqualTo(404);
      share(owner, org, false);
      assertThat(call(org, "GET", path(c), null).statusCode()).isEqualTo(404);
      assertThat(ok(org, "GET", "/research/comparisons", null, 200)).isEmpty();
      assertThat(call(org, "GET", bundle, null).statusCode()).isEqualTo(404);
      ok(owner, "GET", "/simulations/" + target, null, 200);
      share(owner, org, true);
      ok(org, "GET", path(c), null, 200);
      db.update("UPDATE accounts SET enabled=false WHERE id=?", owner.id());
      assertThat(call(org, "GET", bundle, null).statusCode()).isEqualTo(404);
      db.update("UPDATE accounts SET enabled=true WHERE id=?", owner.id());
      db.update("UPDATE organizations SET approved=false WHERE id=?", organization(org));
      assertThat(call(org, "GET", path(c), null).statusCode()).isEqualTo(403);
    } finally {
      for (String name : names) java.nio.file.Files.deleteIfExists(dir.resolve(name));
      java.nio.file.Files.deleteIfExists(dir);
      java.nio.file.Files.deleteIfExists(dir.getParent());
    }
  }

  @Test
  void rejectsInsufficientCapacityAndRollsBackAllDerivedRowsOnLateFailure() throws Exception {
    var owner = actor(null);
    var org = institution();
    var job = submitted(owner, 90, 40);
    share(owner, org, true);
    for (int i = 0; i < 2; i++)
      ok(
          owner,
          "POST",
          "/simulations",
          Map.of("versionId", job.path("versionId").asString(), "requestKey", UUID.randomUUID()),
          202);
    assertThat(
            call(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 2))
                .statusCode())
        .isEqualTo(429);
    assertThat(versions(owner)).isEqualTo(1);
    assertThat(ok(org, "GET", "/research/comparisons", null, 200)).isEmpty();
    db.update(
        "UPDATE simulation_jobs SET state='FAILED' WHERE owner_id=? AND state='QUEUED'",
        owner.id());
    String constraint = "reject_research_" + UUID.randomUUID().toString().replace("-", "");
    db.execute(
        "ALTER TABLE research_comparisons ADD CONSTRAINT "
            + constraint
            + " CHECK(source_job_id <> '"
            + job.path("id").asString()
            + "')");
    try {
      var failure = call(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 2));
      assertThat(failure.statusCode()).isEqualTo(500);
      assertThat(failure.body()).doesNotContain(constraint, "INSERT INTO", "source_job_id");
      assertThat(versions(owner)).isEqualTo(1);
      assertThat(active(owner)).isZero();
      assertThat(ok(org, "GET", "/research/comparisons", null, 200)).isEmpty();
      assertThat(ok(owner, "GET", "/comparisons", null, 200)).isEmpty();
    } finally {
      db.execute("ALTER TABLE research_comparisons DROP CONSTRAINT " + constraint);
    }
  }

  @Test
  void serializesDuplicateRequestsAndConflictingQueueAdmission() throws Exception {
    var owner = actor(null);
    var org = institution();
    var job = submitted(owner, 90, 40);
    share(owner, org, true);
    var request = request(job, UUID.randomUUID(), 2);
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var one = pool.submit(() -> call(org, "POST", "/research/comparisons", request));
      var two = pool.submit(() -> call(org, "POST", "/research/comparisons", request));
      var r1 = one.get(10, java.util.concurrent.TimeUnit.SECONDS);
      var r2 = two.get(10, java.util.concurrent.TimeUnit.SECONDS);
      assertThat(r1.statusCode()).as(r1.body()).isEqualTo(202);
      assertThat(r2.statusCode()).as(r2.body()).isEqualTo(202);
      assertThat(json.readTree(r1.body()).path("id"))
          .isEqualTo(json.readTree(r2.body()).path("id"));
    }
    assertThat(active(owner)).isEqualTo(2);
    assertThat(versions(owner)).isEqualTo(3);
    db.update(
        "UPDATE simulation_jobs SET state='FAILED' WHERE owner_id=? AND state='QUEUED'",
        owner.id());
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var one =
          pool.submit(
              () -> call(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 2)));
      var two =
          pool.submit(
              () -> call(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 2)));
      assertThat(
              List.of(
                  one.get(10, java.util.concurrent.TimeUnit.SECONDS).statusCode(),
                  two.get(10, java.util.concurrent.TimeUnit.SECONDS).statusCode()))
          .containsExactlyInAnyOrder(202, 429);
    }
    assertThat(active(owner)).isEqualTo(2);
    assertThat(versions(owner)).isEqualTo(5);
  }

  @Test
  void boundsOrganizationQueueAcrossDifferentSourceOwners() throws Exception {
    var org = institution();
    for (int i = 0; i < 3; i++) {
      var owner = actor(null);
      var job = submitted(owner, 90, 40);
      share(owner, org, true);
      ok(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 3), 202);
    }
    var fourth = actor(null);
    var job = submitted(fourth, 90, 40);
    share(fourth, org, true);
    assertThat(
            call(org, "POST", "/research/comparisons", request(job, UUID.randomUUID(), 2))
                .statusCode())
        .isEqualTo(429);
    assertThat(versions(fourth)).isEqualTo(1);
    assertThat(active(fourth)).isZero();
  }

  @Test
  void countsEquivalentDecimalPlacementsOnceAndPreservesStoredSources() throws Exception {
    var owner = actor(null);
    var org = institution();
    var jobs = new ArrayList<JsonNode>();
    for (var area : List.of(new java.math.BigDecimal("20"), new java.math.BigDecimal("20.00"))) {
      var job =
          successfulJob(
              owner,
              90,
              List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", area)));
      ok(owner, "POST", "/submissions", Map.of("jobId", job.path("id").asString()), 200);
      jobs.add(job);
    }
    var ids = jobs.stream().map(j -> j.path("id").asString()).toList();
    var originals =
        db.queryForList(
            "SELECT j.id,j.input_hash AS job_hash,v.input_hash AS version_hash,v.placements FROM"
                + " simulation_jobs j JOIN strategy_versions v ON v.id=j.version_id WHERE"
                + " j.owner_id=? ORDER BY j.id",
            owner.id());
    assertThat(originals).hasSize(2);
    assertThat(originals.get(0).get("job_hash")).isNotEqualTo(originals.get(1).get("job_hash"));
    share(owner, org, true);
    var result = ok(org, "POST", "/research/patterns", Map.of("jobIds", ids, "topK", 2), 200);
    assertThat(result.path("method").asString())
        .isEqualTo("SELECTED_UNIQUE_PHYSICAL_TOP_K_WITH_TIES_V2");
    assertThat(result.path("requestedCount").asInt()).isEqualTo(2);
    assertThat(result.path("uniqueInputCount").asInt()).isEqualTo(1);
    assertThat(result.path("duplicateInputCount").asInt()).isEqualTo(1);
    assertThat(result.path("includedCount").asInt()).isEqualTo(1);
    var chosen = result.path("designs").get(0);
    assertThat(chosen.path("jobId").asString())
        .isEqualTo(ids.stream().sorted().findFirst().orElseThrow());
    assertThat(chosen.path("inputHash").asString())
        .isEqualTo(
            originals.stream()
                .filter(row -> row.get("id").toString().equals(chosen.path("jobId").asString()))
                .findFirst()
                .orElseThrow()
                .get("job_hash"));
    assertThat(chosen.path("physicalHash").asString()).matches("[a-f0-9]{64}");
    var single =
        ok(
            org,
            "POST",
            "/research/patterns",
            Map.of("jobIds", List.of(ids.get(1)), "topK", 1),
            200);
    assertThat(single.path("designs").get(0).path("physicalHash"))
        .isEqualTo(chosen.path("physicalHash"));
    assertThat(result.path("placements").get(0).path("frequencyPercent").decimalValue())
        .isEqualByComparingTo("100");
    assertThat(
            db.queryForList(
                "SELECT j.id,j.input_hash AS job_hash,v.input_hash AS version_hash,v.placements"
                    + " FROM simulation_jobs j JOIN strategy_versions v ON v.id=j.version_id WHERE"
                    + " j.owner_id=? ORDER BY j.id",
                owner.id()))
        .isEqualTo(originals);
    assertThat(versions(owner)).isEqualTo(2);
    share(owner, org, false);
    assertThat(
            call(org, "POST", "/research/patterns", Map.of("jobIds", ids, "topK", 2)).statusCode())
        .isEqualTo(404);
  }

  @Test
  void restrictsPatternPopulationAndUsesVerifiedScoresInsteadOfClaimedScores() throws Exception {
    var owner = actor(null);
    var org = institution();
    var a = submitted(owner, 90, 10);
    var b = submitted(owner, 95, 20);
    var c = submitted(owner, 95, 30);
    var duplicate = submitted(owner, 90, 10);
    var ids =
        List.of(
            a.path("id").asString(),
            b.path("id").asString(),
            c.path("id").asString(),
            duplicate.path("id").asString());
    var body = Map.of("jobIds", ids, "topK", 2);
    assertThat(call(org, "POST", "/research/patterns", body).statusCode()).isEqualTo(404);
    share(owner, org, true);
    db.update(
        "UPDATE simulation_jobs SET"
            + " result=REPLACE(result,'\"official\":false','\"score\":9999,\"official\":false')"
            + " WHERE id=?",
        UUID.fromString(a.path("id").asString()));
    var view = ok(org, "POST", "/research/patterns", body, 200);
    assertThat(view.path("uniqueInputCount").asInt()).isEqualTo(3);
    assertThat(view.path("includedCount").asInt()).isEqualTo(3);
    assertThat(view.path("maximumScore").decimalValue()).isEqualByComparingTo("10");
    assertThat(view.path("minimumScore").decimalValue()).isEqualByComparingTo("5");
    assertThat(view.path("placements").get(0).path("meanInstalledAreaM2").decimalValue())
        .isEqualByComparingTo("20");
    assertThat(view.toString()).doesNotContain("designNote", "username", "ownerId");
    assertThat(call(owner, "POST", "/research/patterns", body).statusCode()).isEqualTo(403);
    assertThat(
            call(
                    org,
                    "POST",
                    "/research/patterns",
                    Map.of("jobIds", List.of(ids.get(0), ids.get(0)), "topK", 2))
                .statusCode())
        .isEqualTo(400);
    assertThat(
            call(org, "POST", "/research/patterns", Map.of("jobIds", ids, "topK", 21)).statusCode())
        .isEqualTo(400);
    var foreignBody = new HashMap<>(draft(0, "다른 강우 시험"));
    foreignBody.put(
        "modelHash",
        models.all().stream()
            .map(m -> m.hash())
            .filter(h -> !h.equals(LegacyModelFixtures.HASH))
            .findFirst()
            .orElseThrow());
    var version = ok(owner, "POST", "/strategies", foreignBody, 200);
    var other =
        ok(
            owner,
            "POST",
            "/simulations",
            Map.of("versionId", version.path("id").asString(), "requestKey", UUID.randomUUID()),
            202);
    complete(UUID.fromString(other.path("id").asString()), 90);
    ok(owner, "POST", "/submissions", Map.of("jobId", other.path("id").asString()), 200);
    assertThat(
            call(
                    org,
                    "POST",
                    "/research/patterns",
                    Map.of("jobIds", List.of(ids.get(0), other.path("id").asString()), "topK", 2))
                .statusCode())
        .isEqualTo(422);
    share(owner, org, false);
    assertThat(call(org, "POST", "/research/patterns", body).statusCode()).isEqualTo(404);
  }
}
