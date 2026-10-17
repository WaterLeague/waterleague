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
        "spring.datasource.url=jdbc:h2:mem:research_search;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@ActiveProfiles("local")
class ResearchSearchWorkflowTests {
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
    return actor(org, "MEMBER");
  }

  Actor actor(UUID org, String role) throws Exception {
    UUID id = UUID.randomUUID();
    String name = "qa_" + id.toString().substring(0, 8);
    accounts.add(
        new Account(
            id,
            name,
            name,
            passwords.encode("test-password-1234"),
            role,
            role.equals("ADMIN") ? null : org == null ? "PLAYER" : "INSTITUTION",
            "APPROVED",
            org,
            "",
            "",
            true));
    String secret = org == null && !role.equals("ADMIN") ? null : mfa.provision(id);
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
    var m = (JsonNode) model.view().get("model");
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
    return "/research/searches/" + c.path("id").asString();
  }

  Map<String, Object> searchRequest(List<JsonNode> sources, UUID key, int count) {
    return Map.of(
        "jobIds",
        sources.stream().map(j -> j.path("id").asString()).toList(),
        "requestKey",
        key,
        "topK",
        2,
        "budgetKrw",
        100000000,
        "seed",
        17,
        "candidatesPerArm",
        count);
  }

  int searchCount(Actor a) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM research_searches WHERE organization_id=?",
        Integer.class,
        organization(a));
  }

  int candidateCount(Actor a) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM research_candidates c JOIN research_searches s ON s.id=c.search_id"
            + " WHERE s.organization_id=?",
        Integer.class,
        organization(a));
  }

  UUID finishCandidate(UUID id, int discharge) throws Exception {
    var row =
        db.queryForMap("SELECT model_hash,input_hash FROM research_candidates WHERE id=?", id);
    UUID token = UUID.randomUUID();
    db.update(
        "UPDATE research_candidates SET state='SUCCEEDED',finished_at=CURRENT_TIMESTAMP,result=?"
            + " WHERE id=?",
        json.writeValueAsString(
            Map.of(
                "artifactToken",
                token,
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
                "baseline",
                Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 100),
                "strategy",
                Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", discharge))),
        id);
    return token;
  }

  java.nio.file.Path artifactFixture(UUID id, UUID token) throws Exception {
    // 권한·파일 무결성 시험용 파일. 실제 SWMM 재현 검사는 별도 시나리오에서 수행한다.
    var dir =
        java.nio.file.Path.of(artifactRoot, "research-candidates", id.toString(), token.toString());
    java.nio.file.Files.createDirectories(dir);
    var row =
        db.queryForMap(
            "SELECT model_hash,input_hash,placements,result FROM research_candidates WHERE id=?",
            id);
    var result = (tools.jackson.databind.node.ObjectNode) json.readTree((String) row.get("result"));
    result.without(List.of("artifactToken", "modelHash", "inputHash"));
    Map<String, byte[]> files = new LinkedHashMap<>();
    files.put("builder.py", "TEST_ONLY".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    files.put(
        "model-source.json",
        models
            .require((String) row.get("model_hash"))
            .source()
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    files.put("model.json", "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    files.put(
        "placements.json",
        ((String) row.get("placements")).getBytes(java.nio.charset.StandardCharsets.UTF_8));
    files.put("result.json", json.writeValueAsBytes(result));
    files.put(
        "request.json",
        json.writeValueAsBytes(
            Map.of(
                "modelHash",
                row.get("model_hash"),
                "inputHash",
                row.get("input_hash"),
                "placements",
                json.readTree((String) row.get("placements")))));
    for (String name : List.of("baseline", "strategy", "low", "high"))
      for (String ext : List.of("inp", "rpt", "out"))
        files.put(name + "." + ext, "TEST_ONLY".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    Map<String, String> manifest = new LinkedHashMap<>();
    for (var entry : files.entrySet()) {
      java.nio.file.Files.write(dir.resolve(entry.getKey()), entry.getValue());
      manifest.put(
          entry.getKey(),
          HexFormat.of()
              .formatHex(
                  java.security.MessageDigest.getInstance("SHA-256").digest(entry.getValue())));
    }
    java.nio.file.Files.writeString(
        dir.resolve("manifest.json"), json.writeValueAsString(manifest));
    return dir;
  }

  void removeArtifacts(java.nio.file.Path dir) throws Exception {
    try (var paths = java.nio.file.Files.walk(dir.getParent())) {
      for (var p : paths.sorted(Comparator.reverseOrder()).toList())
        java.nio.file.Files.deleteIfExists(p);
    }
  }

  HttpResponse<byte[]> download(Actor a, String path) throws Exception {
    return a.client()
        .send(
            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
                .build(),
            HttpResponse.BodyHandlers.ofByteArray());
  }

  @Test
  void createsIsolatedCandidatesAndUsesOrganizationIdempotencyWithCurrentPermissions()
      throws Exception {
    var owner = actor(null);
    var org = institution();
    var other = institution();
    var sources = List.of(submitted(owner, 90, 20), submitted(owner, 95, 40));
    int beforeVersions = versions(owner),
        beforeJobs = db.queryForObject("SELECT COUNT(*) FROM simulation_jobs", Integer.class);
    UUID key = UUID.randomUUID();
    var request = searchRequest(sources, key, 1);
    assertThat(call(org, "POST", "/research/searches", request).statusCode()).isEqualTo(404);
    share(owner, org, true);
    share(owner, other, true);
    var response = call(org, "POST", "/research/searches", request);
    assertThat(response.statusCode()).as(response.body()).isEqualTo(202);
    assertThat(response.headers().firstValue("cache-control").orElse("")).contains("no-store");
    var c = json.readTree(response.body());
    assertThat(c.path("candidates").size()).isEqualTo(2);
    assertThat(c.path("sourceBestScore").decimalValue()).isEqualByComparingTo("10");
    assertThat(c.path("completeComparison").asBoolean()).isFalse();
    assertThat(c.path("validationLevel").asString()).isEqualTo("EXPLORATORY");
    var reordered = new HashMap<>(searchRequest(sources.reversed(), key, 1));
    reordered.put("budgetKrw", new java.math.BigDecimal("100000000.00"));
    assertThat(ok(org, "POST", "/research/searches", reordered, 202).path("id"))
        .isEqualTo(c.path("id"));
    var changed = new HashMap<>(request);
    changed.put("seed", 18);
    assertThat(call(org, "POST", "/research/searches", changed).statusCode()).isEqualTo(409);
    assertThat(searchCount(org)).isEqualTo(1);
    assertThat(candidateCount(org)).isEqualTo(2);
    assertThat(versions(owner)).isEqualTo(beforeVersions);
    assertThat(db.queryForObject("SELECT COUNT(*) FROM simulation_jobs", Integer.class))
        .isEqualTo(beforeJobs);
    assertThat(versions(org)).isZero();
    for (var candidate : c.path("candidates")) {
      assertThat(
              call(owner, "GET", "/simulations/" + candidate.path("id").asString(), null)
                  .statusCode())
          .isEqualTo(404);
      assertThat(
              call(org, "GET", "/simulations/" + candidate.path("id").asString(), null)
                  .statusCode())
          .isEqualTo(404);
    }
    assertThat(call(other, "GET", path(c), null).statusCode()).isEqualTo(404);
    assertThat(ok(other, "GET", "/research/searches", null, 200)).isEmpty();
    assertThat(call(owner, "GET", path(c), null).statusCode()).isEqualTo(403);
    ok(actor(organization(org)), "GET", path(c), null, 200);
    var guest = new Actor(UUID.randomUUID(), HttpClient.newHttpClient());
    assertThat(call(guest, "GET", path(c), null).statusCode()).isEqualTo(401);
    var noCsrf =
        org.client()
            .send(
                HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/api/v1/research/searches"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(request)))
                    .build(),
                HttpResponse.BodyHandlers.ofString());
    assertThat(noCsrf.statusCode()).isEqualTo(403);
  }

  @Test
  void revocationOfExcludedTrainingSourceBlocksDetailProvenanceAndBundle() throws Exception {
    var owner = actor(null);
    var excluded = actor(null);
    var org = institution();
    var other = institution();
    var sources =
        List.of(submitted(owner, 90, 20), submitted(owner, 95, 30), submitted(excluded, 99, 40));
    for (var a : List.of(owner, excluded)) {
      share(a, org, true);
      share(a, other, true);
    }
    var c =
        ok(org, "POST", "/research/searches", searchRequest(sources, UUID.randomUUID(), 1), 202);
    assertThat(c.path("generation").path("trainingCount").asInt()).isEqualTo(2);
    var candidate = UUID.fromString(c.path("candidates").get(0).path("id").asString());
    String bundle = path(c) + "/candidates/" + candidate + "/bundle";
    assertThat(call(org, "GET", bundle, null).statusCode()).isEqualTo(409);
    var dir = artifactFixture(candidate, finishCandidate(candidate, 93));
    try {
      var view = ok(org, "GET", path(c), null, 200);
      assertThat(view.path("candidates").get(0).path("score").decimalValue())
          .isEqualByComparingTo("7");
      assertThat(view.path("completeComparison").asBoolean()).isFalse();
      var exported = download(org, bundle);
      assertThat(exported.statusCode()).isEqualTo(200);
      Map<String, byte[]> entries = new LinkedHashMap<>();
      try (var zip =
          new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(exported.body()))) {
        java.util.zip.ZipEntry e;
        while ((e = zip.getNextEntry()) != null) entries.put(e.getName(), zip.readAllBytes());
      }
      assertThat(entries)
          .hasSize(21)
          .containsKeys("manifest.json", "search-provenance.json", "access-scope.json")
          .doesNotContainKey("strategy-history.json");
      var scope = json.readTree(entries.get("access-scope.json"));
      assertThat(scope.path("purpose").asString()).isEqualTo("RESEARCH_PATTERN_SEARCH");
      assertThat(scope.path("sourceJobIds").size()).isEqualTo(3);
      assertThat(scope.path("provenanceHash")).isEqualTo(c.path("provenanceHash"));
      assertThat(json.readTree(entries.get("search-provenance.json")))
          .isEqualTo(c.path("generation"));
      assertThat(ok(org, "GET", path(c) + "/provenance", null, 200))
          .isEqualTo(c.path("generation"));
      assertThat(download(other, bundle).statusCode()).isEqualTo(404);
      share(excluded, org, false);
      assertThat(call(org, "GET", path(c), null).statusCode()).isEqualTo(404);
      assertThat(call(org, "GET", path(c) + "/provenance", null).statusCode()).isEqualTo(404);
      assertThat(download(org, bundle).statusCode()).isEqualTo(404);
      assertThat(ok(org, "GET", "/research/searches", null, 200)).isEmpty();
      ok(owner, "GET", "/simulations/" + sources.get(0).path("id").asString(), null, 200);
      share(excluded, org, true);
      ok(org, "GET", path(c), null, 200);
      db.update("UPDATE accounts SET enabled=false WHERE id=?", excluded.id());
      assertThat(download(org, bundle).statusCode()).isEqualTo(404);
      db.update("UPDATE accounts SET enabled=true WHERE id=?", excluded.id());
      db.update("UPDATE organizations SET approved=false WHERE id=?", organization(org));
      assertThat(call(org, "GET", path(c), null).statusCode()).isEqualTo(403);
    } finally {
      removeArtifacts(dir);
    }
  }

  @Test
  void defaultsToEqualThreeCandidateArmsAndNeverUsesReportedScoreForComparison() throws Exception {
    var owner = actor(null);
    var org = institution();
    var sources = List.of(submitted(owner, 90, 20), submitted(owner, 95, 40));
    share(owner, org, true);
    var request = new HashMap<>(searchRequest(sources, UUID.randomUUID(), 1));
    request.remove("candidatesPerArm");
    var c = ok(org, "POST", "/research/searches", request, 202);
    assertThat(c.path("candidates").size()).isEqualTo(6);
    for (var candidate : c.path("candidates"))
      finishCandidate(UUID.fromString(candidate.path("id").asString()), 93);
    var view = ok(org, "GET", path(c), null, 200);
    assertThat(view.path("completeComparison").asBoolean()).isTrue();
    for (var arm : view.path("arms")) {
      assertThat(arm.path("total").asInt()).isEqualTo(3);
      assertThat(arm.path("succeeded").asInt()).isEqualTo(3);
      assertThat(arm.path("bestScore").decimalValue()).isEqualByComparingTo("7");
    }
    db.update(
        "UPDATE research_candidates SET state='FAILED',result=NULL,error_code='SIMULATION_TIMEOUT'"
            + " WHERE id=?",
        UUID.fromString(c.path("candidates").get(0).path("id").asString()));
    assertThat(ok(org, "GET", path(c), null, 200).path("completeComparison").asBoolean()).isFalse();
  }

  @Test
  void serializesMatchingRequestsAndBoundsCompetingSearchesAtomically() throws Exception {
    var a = actor(null);
    var b = actor(null);
    var org = institution();
    var sources = List.of(submitted(a, 90, 20), submitted(b, 95, 40));
    share(a, org, true);
    share(b, org, true);
    UUID key = UUID.randomUUID();
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var one =
          pool.submit(
              () -> call(org, "POST", "/research/searches", searchRequest(sources, key, 3)));
      var two =
          pool.submit(
              () ->
                  call(
                      org,
                      "POST",
                      "/research/searches",
                      searchRequest(sources.reversed(), key, 3)));
      var r1 = one.get(10, java.util.concurrent.TimeUnit.SECONDS);
      var r2 = two.get(10, java.util.concurrent.TimeUnit.SECONDS);
      assertThat(r1.statusCode()).as(r1.body()).isEqualTo(202);
      assertThat(r2.statusCode()).as(r2.body()).isEqualTo(202);
      assertThat(json.readTree(r1.body()).path("id"))
          .isEqualTo(json.readTree(r2.body()).path("id"));
    }
    assertThat(searchCount(org)).isEqualTo(1);
    assertThat(candidateCount(org)).isEqualTo(6);
    db.update(
        "UPDATE research_candidates SET state='FAILED' WHERE search_id IN (SELECT id FROM"
            + " research_searches WHERE organization_id=?)",
        organization(org));
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var one =
          pool.submit(
              () ->
                  call(
                      org,
                      "POST",
                      "/research/searches",
                      searchRequest(sources, UUID.randomUUID(), 3)));
      var two =
          pool.submit(
              () ->
                  call(
                      org,
                      "POST",
                      "/research/searches",
                      searchRequest(sources.reversed(), UUID.randomUUID(), 3)));
      assertThat(
              List.of(
                  one.get(10, java.util.concurrent.TimeUnit.SECONDS).statusCode(),
                  two.get(10, java.util.concurrent.TimeUnit.SECONDS).statusCode()))
          .containsExactlyInAnyOrder(202, 429);
    }
    assertThat(searchCount(org)).isEqualTo(2);
    assertThat(candidateCount(org)).isEqualTo(12);
    assertThat(active(a)).isZero();
    assertThat(active(b)).isZero();
    assertThat(versions(a)).isEqualTo(1);
    assertThat(versions(b)).isEqualTo(1);
  }

  @Test
  void rollsBackSearchSourcesAndAllCandidatesAfterLateInsertFailure() throws Exception {
    var owner = actor(null);
    var org = institution();
    var sources = List.of(submitted(owner, 90, 20), submitted(owner, 95, 40));
    share(owner, org, true);
    String constraint = "reject_search_" + UUID.randomUUID().toString().replace("-", "");
    // 새 기관의 후보 두 번째 행에서만 실패시키고 앞서 삽입한 행도 함께 취소되는지 확인한다.
    UUID key = UUID.randomUUID();
    db.execute(
        "ALTER TABLE research_candidates ADD CONSTRAINT "
            + constraint
            + " CHECK(ordinal<>2 OR created_at<CAST('"
            + java.time.Instant.now()
            + "' AS TIMESTAMP WITH TIME ZONE))");
    try {
      var response = call(org, "POST", "/research/searches", searchRequest(sources, key, 2));
      assertThat(response.statusCode()).isEqualTo(500);
      assertThat(response.body()).doesNotContain(constraint, "INSERT INTO", "Exception");
      assertThat(searchCount(org)).isZero();
      assertThat(candidateCount(org)).isZero();
    } finally {
      db.execute("ALTER TABLE research_candidates DROP CONSTRAINT " + constraint);
    }
  }

  @Test
  void rejectsMixedModelsPhysicalDuplicatesInvalidBudgetAndCorruptSource() throws Exception {
    var owner = actor(null);
    var org = institution();
    var a = submitted(owner, 90, 20);
    var b = submitted(owner, 95, 40);
    share(owner, org, true);
    var sources = List.of(a, b);
    var invalid = new HashMap<>(searchRequest(sources, UUID.randomUUID(), 1));
    invalid.put("budgetKrw", 100);
    assertThat(call(org, "POST", "/research/searches", invalid).statusCode()).isEqualTo(422);
    invalid.put("budgetKrw", new java.math.BigDecimal("99999999.5"));
    assertThat(call(org, "POST", "/research/searches", invalid).statusCode()).isEqualTo(400);
    var duplicate = submitted(owner, 90, 20);
    var same =
        call(
            org,
            "POST",
            "/research/searches",
            searchRequest(List.of(a, duplicate), UUID.randomUUID(), 1));
    assertThat(same.statusCode()).isEqualTo(422);
    assertThat(same.body()).contains("SEARCH_SAMPLE_INSUFFICIENT");
    var body = new HashMap<>(draft(0, "다른 모델 시험"));
    body.put(
        "modelHash",
        models.all().stream()
            .map(m -> m.hash())
            .filter(h -> !h.equals(model.hash()))
            .findFirst()
            .orElseThrow());
    var v = ok(owner, "POST", "/strategies", body, 200);
    var other =
        ok(
            owner,
            "POST",
            "/simulations",
            Map.of("versionId", v.path("id").asString(), "requestKey", UUID.randomUUID()),
            202);
    complete(UUID.fromString(other.path("id").asString()), 90);
    ok(owner, "POST", "/submissions", Map.of("jobId", other.path("id").asString()), 200);
    assertThat(
            call(
                    org,
                    "POST",
                    "/research/searches",
                    searchRequest(List.of(a, other), UUID.randomUUID(), 1))
                .statusCode())
        .isEqualTo(422);
    db.update(
        "UPDATE simulation_jobs SET input_hash=? WHERE id=?",
        "0".repeat(64),
        UUID.fromString(a.path("id").asString()));
    var corrupt =
        call(org, "POST", "/research/searches", searchRequest(sources, UUID.randomUUID(), 1));
    assertThat(corrupt.statusCode()).isEqualTo(422);
    assertThat(corrupt.body()).contains("RESULT_QUALITY_FAILED");
    assertThat(searchCount(org)).isZero();
  }

  @Test
  void checksProvenanceCandidateAndArtifactIntegrityBeforeExport() throws Exception {
    var owner = actor(null);
    var org = institution();
    var sources = List.of(submitted(owner, 90, 20), submitted(owner, 95, 40));
    share(owner, org, true);
    var c =
        ok(org, "POST", "/research/searches", searchRequest(sources, UUID.randomUUID(), 1), 202);
    UUID search = UUID.fromString(c.path("id").asString()),
        candidate = UUID.fromString(c.path("candidates").get(0).path("id").asString());
    var cost =
        db.queryForObject(
            "SELECT cost FROM research_candidates WHERE id=?",
            java.math.BigDecimal.class,
            candidate);
    db.update("UPDATE research_candidates SET cost=cost+1 WHERE id=?", candidate);
    assertThat(call(org, "GET", path(c), null).statusCode()).isEqualTo(422);
    db.update("UPDATE research_candidates SET cost=? WHERE id=?", cost, candidate);
    db.update("UPDATE research_searches SET provenance_hash=? WHERE id=?", "0".repeat(64), search);
    assertThat(call(org, "GET", path(c) + "/provenance", null).statusCode()).isEqualTo(422);
    db.update(
        "UPDATE research_searches SET provenance_hash=? WHERE id=?",
        c.path("provenanceHash").asString(),
        search);
    var dir = artifactFixture(candidate, finishCandidate(candidate, 93));
    var outside = java.nio.file.Files.createTempFile("waterleague-export-sentinel-", ".txt");
    java.nio.file.Files.writeString(outside, "PRIVATE_SENTINEL");
    String bundle = path(c) + "/candidates/" + candidate + "/bundle";
    try {
      assertThat(download(org, bundle).statusCode()).isEqualTo(200);
      var file = dir.resolve("builder.py");
      var original = java.nio.file.Files.readAllBytes(file);
      java.nio.file.Files.writeString(file, "DAMAGED");
      assertThat(call(org, "GET", bundle, null).statusCode()).isEqualTo(422);
      java.nio.file.Files.delete(file);
      java.nio.file.Files.createSymbolicLink(file, outside);
      var symlink = call(org, "GET", bundle, null);
      assertThat(symlink.statusCode()).isEqualTo(422);
      assertThat(symlink.body())
          .doesNotContain("PRIVATE_SENTINEL", outside.toString(), dir.toString());
      java.nio.file.Files.delete(file);
      java.nio.file.Files.createLink(file, outside);
      assertThat(call(org, "GET", bundle, null).statusCode()).isEqualTo(422);
      java.nio.file.Files.delete(file);
      java.nio.file.Files.write(file, original);
      assertThat(download(org, bundle).statusCode()).isEqualTo(200);
      assertThat(java.nio.file.Files.readString(outside)).isEqualTo("PRIVATE_SENTINEL");
      assertThat(
              call(org, "GET", path(c) + "/candidates/" + UUID.randomUUID() + "/bundle", null)
                  .statusCode())
          .isEqualTo(404);
    } finally {
      java.nio.file.Files.deleteIfExists(outside);
      removeArtifacts(dir);
    }
  }

  @Test
  void rechecksConsentAfterOwnerLockAndSharesCreationRateAcrossOrganization() throws Exception {
    var owner = actor(null);
    var org = institution();
    var colleague = actor(organization(org));
    var sources = List.of(submitted(owner, 90, 20), submitted(owner, 95, 40));
    share(owner, org, true);
    var request = searchRequest(sources, UUID.randomUUID(), 1);
    var template = new org.springframework.transaction.support.TransactionTemplate(transactions);
    var started = new java.util.concurrent.CountDownLatch(1);
    try (var pool = java.util.concurrent.Executors.newSingleThreadExecutor()) {
      var future =
          template.execute(
              status -> {
                research.ownerLock(owner.id());
                var pending =
                    pool.submit(
                        () -> {
                          started.countDown();
                          return call(org, "POST", "/research/searches", request);
                        });
                try {
                  assertThat(started.await(3, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
                  assertThatThrownBy(
                          () -> pending.get(200, java.util.concurrent.TimeUnit.MILLISECONDS))
                      .isInstanceOf(java.util.concurrent.TimeoutException.class);
                  research.consent(owner.id(), organization(org), false);
                } catch (Exception e) {
                  throw new RuntimeException(e);
                }
                return pending;
              });
      assertThat(future.get(10, java.util.concurrent.TimeUnit.SECONDS).statusCode()).isEqualTo(404);
    }
    assertThat(searchCount(org)).isZero();
    share(owner, org, true);
    db.update("DELETE FROM rate_limits WHERE bucket_key=?", "research-search:" + organization(org));
    for (int i = 0; i < 6; i++)
      ok(i % 2 == 0 ? org : colleague, "POST", "/research/searches", request, 202);
    assertThat(call(colleague, "POST", "/research/searches", request).statusCode()).isEqualTo(429);
    assertThat(searchCount(org)).isEqualTo(1);
    assertThat(candidateCount(org)).isEqualTo(2);
  }

  @Test
  void combinedRainfallAndCandidateCapacityCannotExceedOrganizationAllowance() throws Exception {
    var org = institution();
    var sourceOwner = actor(null);
    var source = submitted(sourceOwner, 90, 40);
    share(sourceOwner, org, true);
    ok(org, "POST", "/research/comparisons", request(source, UUID.randomUUID(), 3), 202);
    var a = actor(null);
    var b = actor(null);
    var sources = List.of(submitted(a, 90, 20), submitted(b, 95, 40));
    share(a, org, true);
    share(b, org, true);
    assertThat(
            call(org, "POST", "/research/searches", searchRequest(sources, UUID.randomUUID(), 4))
                .statusCode())
        .isEqualTo(429);
    assertThat(searchCount(org)).isZero();
    assertThat(candidateCount(org)).isZero();
    ok(org, "POST", "/research/searches", searchRequest(sources, UUID.randomUUID(), 3), 202);
    var another = actor(null);
    var original = submitted(another, 90, 40);
    share(another, org, true);
    assertThat(
            call(org, "POST", "/research/comparisons", request(original, UUID.randomUUID(), 2))
                .statusCode())
        .isEqualTo(429);
    assertThat(active(another)).isZero();
    assertThat(versions(another)).isEqualTo(1);
  }

  @Test
  void refusesAdministratorAndSessionWithoutVerifiedMfa() throws Exception {
    var admin = actor(null, "ADMIN");
    assertThat(call(admin, "GET", "/research/searches", null).statusCode()).isEqualTo(403);
    var org = institution();
    ok(org, "GET", "/research/searches", null, 200);
    db.update(
        "DELETE FROM spring_session_attributes WHERE attribute_name='mfaVerified' AND"
            + " session_primary_id IN (SELECT primary_id FROM spring_session WHERE"
            + " principal_name=?)",
        accounts.byId(org.id()).orElseThrow().username());
    assertThat(call(org, "GET", "/research/searches", null).statusCode()).isEqualTo(401);
  }

  void python(java.nio.file.Path work, List<String> arguments) throws Exception {
    var root = java.nio.file.Path.of("..").toRealPath();
    List<String> command = new ArrayList<>();
    command.add(System.getProperty("waterleague.integration.python"));
    command.addAll(arguments);
    var log = work.resolve(UUID.randomUUID() + ".log");
    var builder =
        new ProcessBuilder(command)
            .directory(root.toFile())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile());
    builder
        .environment()
        .keySet()
        .removeIf(
            k ->
                !Set.of(
                        "PATH",
                        "HOME",
                        "LANG",
                        "LC_ALL",
                        "TMPDIR",
                        "WL_INTEGRATION_USER",
                        "WL_INTEGRATION_PASSWORD")
                    .contains(k));
    builder.environment().put("PYTHONPATH", root.resolve("simulation").toString());
    var process = builder.start();
    if (!process.waitFor(120, java.util.concurrent.TimeUnit.SECONDS)) {
      process.destroyForcibly();
      throw new AssertionError("격리 물리 재현 검사 시간 초과");
    }
    assertThat(process.exitValue()).as(java.nio.file.Files.readString(log)).isZero();
  }

  void calculate(java.nio.file.Path work, String kind, List<String> ids) throws Exception {
    List<String> args =
        new ArrayList<>(
            List.of(
                "simulation/integration/search_workflow.py",
                "--jdbc",
                System.getProperty("waterleague.integration.jdbc"),
                "--artifacts",
                java.nio.file.Path.of(artifactRoot).toRealPath().toString(),
                "--work",
                work.toString(),
                "--kind",
                kind));
    args.addAll(ids);
    python(work, args);
  }

  @Test
  void replaysActualSwmmSourcesAndGeneratedCandidateBundleOnIsolatedPostgres() throws Exception {
    org.junit.jupiter.api.Assumptions.assumeTrue(
        System.getProperty("waterleague.integration.python") != null,
        "실제 엔진 검사는 --suite search 격리 PostgreSQL 실행에서 수행");
    var work =
        java.nio.file.Files.createTempDirectory(
            java.nio.file.Path.of("target").toRealPath(), "search-physics-");
    java.nio.file.Files.createDirectories(java.nio.file.Path.of(artifactRoot));
    var owner = actor(null);
    var org = institution();
    List<JsonNode> sources = new ArrayList<>();
    List<String> candidates = new ArrayList<>();
    try {
      for (int area : List.of(20, 40)) {
        var body = new HashMap<>(draft(0, "격리 SWMM 재현 시험"));
        body.put(
            "placements",
            List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", area)));
        var version = ok(owner, "POST", "/strategies", body, 200);
        sources.add(
            ok(
                owner,
                "POST",
                "/simulations",
                Map.of("versionId", version.path("id").asString(), "requestKey", UUID.randomUUID()),
                202));
      }
      calculate(work, "PERSONAL", sources.stream().map(s -> s.path("id").asString()).toList());
      for (var source : sources)
        ok(owner, "POST", "/submissions", Map.of("jobId", source.path("id").asString()), 200);
      share(owner, org, true);
      var search =
          ok(org, "POST", "/research/searches", searchRequest(sources, UUID.randomUUID(), 1), 202);
      for (var c : search.path("candidates")) candidates.add(c.path("id").asString());
      calculate(work, "RESEARCH_CANDIDATE", candidates);
      var detail = ok(org, "GET", path(search), null, 200);
      assertThat(detail.path("completeComparison").asBoolean()).isTrue();
      assertThat(versions(owner)).isEqualTo(2);
      assertThat(versions(org)).isZero();
      for (var candidate : detail.path("candidates")) {
        assertThat(candidate.path("state").asString()).isEqualTo("SUCCEEDED");
        assertThat(candidate.path("result").path("engine").path("binarySha256").asString())
            .matches("[a-f0-9]{64}");
        var download =
            download(
                org, path(search) + "/candidates/" + candidate.path("id").asString() + "/bundle");
        assertThat(download.statusCode())
            .as(new String(download.body(), java.nio.charset.StandardCharsets.UTF_8))
            .isEqualTo(200);
        var bundle = work.resolve(candidate.path("id").asString() + ".zip");
        java.nio.file.Files.write(bundle, download.body());
        python(work, List.of("scripts/verify_bundle.py", bundle.toString(), "--rerun"));
        try (var zip = new java.util.zip.ZipFile(bundle.toFile())) {
          assertThat(zip.size()).isEqualTo(21);
          for (String name : List.of("search-provenance.json", "model-source.json"))
            try (var input = zip.getInputStream(zip.getEntry(name))) {
              java.nio.file.Files.write(work.resolve(name), input.readAllBytes());
            }
        }
        python(
            work,
            List.of(
                "scripts/verify_search.py",
                work.resolve("search-provenance.json").toString(),
                "--model",
                work.resolve("model-source.json").toString()));
      }
      share(owner, org, false);
      assertThat(call(org, "GET", path(search), null).statusCode()).isEqualTo(404);
      assertThat(call(org, "GET", path(search) + "/provenance", null).statusCode()).isEqualTo(404);
      assertThat(
              download(org, path(search) + "/candidates/" + candidates.getFirst() + "/bundle")
                  .statusCode())
          .isEqualTo(404);
    } finally {
      List<java.nio.file.Path> roots = new ArrayList<>();
      roots.add(work);
      for (var s : sources) roots.add(java.nio.file.Path.of(artifactRoot, s.path("id").asString()));
      for (var id : candidates)
        roots.add(java.nio.file.Path.of(artifactRoot, "research-candidates", id));
      for (var root : roots)
        if (java.nio.file.Files.exists(root))
          try (var files = java.nio.file.Files.walk(root)) {
            for (var file : files.sorted(Comparator.reverseOrder()).toList())
              java.nio.file.Files.delete(file);
          }
    }
  }
}
