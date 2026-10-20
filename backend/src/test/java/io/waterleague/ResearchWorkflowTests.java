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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class ResearchWorkflowTests extends PostgresIntegrationTest {
  @Value("${local.server.port}")
  int port;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired LabModelService model;
  @Autowired io.waterleague.account.service.InstitutionMfaService mfa;
  @Autowired io.waterleague.common.service.JsonService documentJson;

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
        NativeResearchFixtures.HASH,
        "placements",
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 10)),
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
    assertThat(v.get("cost").decimalValue()).isEqualByComparingTo("5600000");
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
            NativeResearchFixtures.HASH,
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
    assertThat(details.get("lab").get("modelHash").asString())
        .isEqualTo(NativeResearchFixtures.HASH);
    assertThat(details.toString()).doesNotContain("미제출 비공개 후속 메모", "passwordHash", "username");
    // 이전 계산은 현재 강우로 대체하지 않고 해시가 일치하는 보관 모델을 사용한다.
    var archived =
        (tools.jackson.databind.node.ObjectNode)
            json.valueToTree(model.view(NativeResearchFixtures.HASH).get("model"));
    ((tools.jackson.databind.node.ObjectNode) archived.get("rainfall")).put("source", "이전 시험 강우");
    String source = json.writeValueAsString(archived);
    String archiveHash = documentJson.hash(source);
    UUID artifactToken = UUID.randomUUID();
    var storedResult = new HashMap<String, Object>(result);
    storedResult.put("modelHash", archiveHash);
    storedResult.put("artifactToken", artifactToken.toString());
    db.update(
        "UPDATE simulation_jobs SET model_hash=?,result=? WHERE id=?",
        archiveHash,
        json.writeValueAsString(storedResult),
        id);
    var folder = java.nio.file.Path.of(artifactRoot, id.toString(), artifactToken.toString());
    java.nio.file.Files.createDirectories(folder);
    var modelFile = folder.resolve("model-source.json");
    try {
      java.nio.file.Files.writeString(modelFile, source);
      var oldDetails = ok(a, "GET", "/research/strategies/" + id, null, 200);
      assertThat(oldDetails.get("lab").get("modelHash").asString()).isEqualTo(archiveHash);
      assertThat(oldDetails.get("lab").get("model").get("rainfall").get("source").asString())
          .isEqualTo("이전 시험 강우");
      java.nio.file.Files.writeString(modelFile, source + " ");
      assertThat(call(a, "GET", "/research/strategies/" + id, null).statusCode()).isEqualTo(422);
    } finally {
      java.nio.file.Files.deleteIfExists(modelFile);
      java.nio.file.Files.deleteIfExists(folder);
      java.nio.file.Files.deleteIfExists(folder.getParent());
    }
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

  @Test
  void usesNewGeometryByDefaultWithoutReinterpretingLegacyPlacements() throws Exception {
    var player = actor(null);
    var current = ok(player, "GET", "/lab", null, 200);
    String hash = current.path("modelHash").asString();
    assertThat(hash).isNotEqualTo(NativeResearchFixtures.HASH);
    assertThat(current.path("model").path("mapId").asString()).isEqualTo("seongsu-ngii-2025-v2");
    var input = new HashMap<>(draft(0, "신규 공개 지도 검사"));
    input.put("modelHash", hash);
    input.put(
        "placements", List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 40)));
    assertThat(call(player, "POST", "/strategies", input).statusCode()).isEqualTo(422);
    input.put(
        "placements", List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 20)));
    var version = ok(player, "POST", "/strategies", input, 200);
    assertThat(version.path("modelHash").asString()).isEqualTo(hash);
    var legacy = ok(player, "POST", "/strategies", draft(0, "이전 지도 검사"), 200);
    assertThat(legacy.path("modelHash").asString()).isEqualTo(NativeResearchFixtures.HASH);
    var compatibility = new io.waterleague.comparison.service.ComparisonCompatibilityService();
    var original = ok(player, "GET", "/lab?modelHash=" + NativeResearchFixtures.HASH, null, 200);
    assertThatCode(() -> compatibility.require(original.path("model"), current.path("model")))
        .doesNotThrowAnyException();
    assertThat(call(player, "GET", "/lab?modelHash=" + LegacyModelFixtures.HASH, null).statusCode())
        .isEqualTo(404);
  }

  @Test
  void separatesRainfallVersionsBoardsAndLeagueModels() throws Exception {
    var player = actor(null);
    var catalog = ok(player, "GET", "/lab/catalog", null, 200).get("models");
    try (var source = getClass().getResourceAsStream("/models/current/catalog.json")) {
      var registered =
          json.readTree(new String(source.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8))
              .path("models");
      assertThat(
              java.util.stream.StreamSupport.stream(catalog.spliterator(), false)
                  .map(model -> model.path("modelHash").asString())
                  .toList())
          .containsExactlyInAnyOrderElementsOf(
              java.util.stream.StreamSupport.stream(registered.spliterator(), false)
                  .map(model -> model.path("sha256").asString())
                  .toList());
    }
    assertThat(
            java.util.stream.StreamSupport.stream(catalog.spliterator(), false)
                .filter(
                    m ->
                        m.path("regionalRainfallUse")
                            .asString()
                            .equals("NEAREST_AWS_OBSERVED_REPLAY"))
                .count())
        .isZero();
    String first = catalog.get(1).get("modelHash").asString();
    String second = catalog.get(2).get("modelHash").asString();
    assertThat(
            ok(player, "GET", "/lab?modelHash=" + first, null, 200)
                .get("model")
                .get("rainfall")
                .get("totalDepthMm")
                .decimalValue())
        .isEqualByComparingTo("18.5");
    assertThat(call(player, "GET", "/lab?modelHash=" + "0".repeat(64), null).statusCode())
        .isEqualTo(404);
    var input = new HashMap<>(draft(0, "강우 분리 검사"));
    input.put("modelHash", first);
    var version = ok(player, "POST", "/strategies", input, 200);
    input.put("modelHash", second);
    input.put("baseRevision", 1);
    assertThat(
            call(
                    player,
                    "POST",
                    "/strategies/" + version.get("strategyId").asString() + "/versions",
                    input)
                .statusCode())
        .isEqualTo(409);
    var job =
        ok(
            player,
            "POST",
            "/simulations",
            Map.of("versionId", version.get("id").asString(), "requestKey", UUID.randomUUID()),
            202);
    assertThat(job.get("modelHash").asString()).isEqualTo(first);
    UUID id = UUID.fromString(job.get("id").asString());
    // H2 통합 검사 전용 고정값. 운영 순위에 사용하지 않는다.
    db.update(
        "UPDATE simulation_jobs SET state='SUCCEEDED',result=? WHERE id=?",
        json.writeValueAsString(
            Map.of(
                "modelHash",
                first,
                "inputHash",
                version.get("inputHash").asString(),
                "validationLevel",
                "EXPLORATORY",
                "official",
                false,
                "baseline",
                Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 100),
                "strategy",
                Map.of("runoffContinuityPercent", 0, "accountedDischargeM3", 90))),
        id);
    ok(player, "POST", "/submissions", Map.of("jobId", id), 200);
    assertThat(
            db.queryForObject(
                "SELECT model_hash FROM submissions WHERE job_id=?", String.class, id))
        .isEqualTo(first);
    String name = accounts.byId(player.id()).orElseThrow().displayName();
    assertThat(call(player, "GET", "/leaderboard?modelHash=" + first, null).body()).contains(name);
    assertThat(call(player, "GET", "/leaderboard?modelHash=" + second, null).body())
        .doesNotContain(name);
    var org = institution();
    var rules = new HashMap<>(leagueDraft(0, 10, 30000000));
    rules.put("modelHash", second);
    var league = ok(org, "POST", "/institution/leagues", rules, 200);
    assertThat(league.get("rules").get("modelHash").asString()).isEqualTo(second);
    assertThat(league.get("playable").asBoolean()).isTrue();
    var published =
        ok(
            org,
            "POST",
            "/institution/leagues/" + league.get("id").asString() + "/publish",
            Map.of("revision", 1, "rulesHash", league.get("rulesHash").asString()),
            200);
    assertThat(published.get("playable").asBoolean()).isTrue();
    ok(
        player,
        "PUT",
        "/consents/" + accounts.byId(org.id()).orElseThrow().organizationId(),
        Map.of("granted", true),
        200);
    assertThat(call(org, "GET", "/research/strategies?modelHash=" + first, null).body())
        .contains(id.toString());
    assertThat(call(org, "GET", "/research/strategies?modelHash=" + second, null).body())
        .doesNotContain(id.toString());
  }

  Map<String, Object> leagueDraft(int revision, int limit, long budget) {
    return Map.of(
        "modelHash",
        NativeResearchFixtures.HASH,
        "baseRevision",
        revision,
        "title",
        "동일 강우 실험",
        "question",
        "같은 비용에서 배치 효과 비교",
        "opensAt",
        java.time.Instant.now().minusSeconds(10).toString(),
        "closesAt",
        java.time.Instant.now().plusSeconds(3600).toString(),
        "budget",
        budget,
        "allowedTypes",
        List.of("RAIN_GARDEN"),
        "submissionLimit",
        limit);
  }

  Actor institution() throws Exception {
    UUID org = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", org, "리그 시험 기관");
    return actor(org);
  }

  JsonNode publishedLeague(Actor org, int limit, long budget) throws Exception {
    var l = ok(org, "POST", "/institution/leagues", leagueDraft(0, limit, budget), 200);
    return ok(
        org,
        "POST",
        "/institution/leagues/" + l.get("id").asString() + "/publish",
        Map.of("revision", 1, "rulesHash", l.get("rulesHash").asString()),
        200);
  }

  JsonNode successfulJob(Actor player, int discharge) throws Exception {
    return successfulJob(
        player,
        discharge,
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 10)));
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
    var m = (JsonNode) model.view(NativeResearchFixtures.HASH).get("model");
    var result =
        Map.of(
            "modelHash",
            NativeResearchFixtures.HASH,
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

  Map<String, Object> leagueSubmission(JsonNode league, JsonNode job) {
    return Map.of(
        "jobId", job.get("id").asString(), "rulesHash", league.get("rulesHash").asString());
  }

  @Test
  void validatesPlacementLimitsAndAwardTerms() throws Exception {
    var org = institution();
    var basic = ok(org, "POST", "/institution/leagues", leagueDraft(0, 10, 300000000), 200);
    var rules = basic.path("rules");
    assertThat(rules.path("schemaVersion").asInt()).isEqualTo(2);
    assertThat(rules.path("placementLimit").asInt()).isPositive();
    assertThat(rules.path("award").path("prizeKrw").asLong()).isZero();
    var input = new HashMap<>(leagueDraft(0, 10, 300000000));
    for (var patch :
        List.of(
            Map.of("placementLimit", rules.path("placementLimit").asInt() + 1),
            Map.of(
                "areaLimitM2",
                rules.path("areaLimitM2").decimalValue().add(new java.math.BigDecimal("0.01"))),
            Map.of("areaLimitM2", 1.001),
            Map.of("award", Map.of("prizeKrw", -1, "winnerCount", 0, "notice", "")),
            Map.of(
                "award", Map.of("prizeKrw", 100000, "winnerCount", 0, "notice", "선정 기준과 지급 일정 안내")),
            Map.of("award", Map.of("prizeKrw", 0, "winnerCount", 1, "notice", "")),
            Map.of("award", Map.of("prizeKrw", 100000, "winnerCount", 1, "notice", "짧음")))) {
      var invalid = new HashMap<>(input);
      invalid.putAll(patch);
      assertThat(call(org, "POST", "/institution/leagues", invalid).statusCode()).isEqualTo(400);
    }
    input.put("placementLimit", 2);
    input.put("areaLimitM2", 40.03);
    input.put(
        "award", Map.of("prizeKrw", 100000, "winnerCount", 1, "notice", "로컬 시험 선정 기준과 지급 일정 안내"));
    var created = ok(org, "POST", "/institution/leagues", input, 200);
    input.put("baseRevision", 1);
    input.put(
        "award",
        Map.of("prizeKrw", 200000, "winnerCount", 2, "notice", "수정된 로컬 시험 선정 기준과 지급 일정 안내"));
    var updated =
        ok(org, "PUT", "/institution/leagues/" + created.path("id").asString(), input, 200);
    assertThat(updated.path("rulesHash").asString())
        .isNotEqualTo(created.path("rulesHash").asString());
    var path = "/institution/leagues/" + created.path("id").asString();
    assertThat(
            call(
                    org,
                    "POST",
                    path + "/publish",
                    Map.of("revision", 2, "rulesHash", created.path("rulesHash").asString()))
                .statusCode())
        .isEqualTo(409);
    ok(
        org,
        "POST",
        path + "/publish",
        Map.of("revision", 2, "rulesHash", updated.path("rulesHash").asString()),
        200);
    input.put("baseRevision", 3);
    assertThat(call(org, "PUT", path, input).statusCode()).isEqualTo(409);
  }

  @Test
  void enforcesCountAndDecimalAreaAtSubmission() throws Exception {
    var org = institution();
    var player = actor(null);
    var input = new HashMap<>(leagueDraft(0, 10, 300000000));
    input.put("placementLimit", 1);
    input.put("areaLimitM2", 10);
    var draft = ok(org, "POST", "/institution/leagues", input, 200);
    var league =
        ok(
            org,
            "POST",
            "/institution/leagues/" + draft.path("id").asString() + "/publish",
            Map.of("revision", 1, "rulesHash", draft.path("rulesHash").asString()),
            200);
    var endpoint = "/leagues/" + league.path("id").asString() + "/submissions";
    var exact = successfulJob(player, 90);
    ok(player, "POST", endpoint, leagueSubmission(league, exact), 200);
    var area =
        successfulJob(
            player,
            90,
            List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 10.01)));
    var count =
        successfulJob(
            player,
            90,
            List.of(
                Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 20),
                Map.of("cellId", "G2", "facilityType", "RAIN_GARDEN", "areaM2", 20)));
    assertThat(call(player, "POST", endpoint, leagueSubmission(league, area)).statusCode())
        .isEqualTo(422);
    assertThat(call(player, "POST", endpoint, leagueSubmission(league, count)).statusCode())
        .isEqualTo(422);
    input.put("placementLimit", 2);
    input.put("areaLimitM2", 10.03);
    var other = ok(org, "POST", "/institution/leagues", input, 200);
    other =
        ok(
            org,
            "POST",
            "/institution/leagues/" + other.path("id").asString() + "/publish",
            Map.of("revision", 1, "rulesHash", other.path("rulesHash").asString()),
            200);
    var decimal =
        successfulJob(
            player,
            90,
            List.of(
                Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 2.51),
                Map.of("cellId", "G2", "facilityType", "RAIN_GARDEN", "areaM2", 7.52)));
    ok(
        player,
        "POST",
        "/leagues/" + other.path("id").asString() + "/submissions",
        leagueSubmission(other, decimal),
        200);
  }

  @Test
  void preservesLegacyRulesWithoutRewritingTheirHash() throws Exception {
    var org = institution();
    var player = actor(null);
    var league = publishedLeague(org, 2, 300000000);
    UUID id = UUID.fromString(league.path("id").asString());
    var old = (tools.jackson.databind.node.ObjectNode) league.path("rules").deepCopy();
    old.put("schemaVersion", 1);
    old.remove("placementLimit");
    old.remove("areaLimitM2");
    old.remove("award");
    String original = json.writeValueAsString(old);
    String hash = documentJson.hash(original);
    db.update("UPDATE leagues SET rules=?,rules_hash=? WHERE id=?", original, hash, id);
    var viewed = ok(player, "GET", "/leagues/" + id, null, 200).path("league");
    assertThat(viewed.path("rules").has("placementLimit")).isFalse();
    assertThat(viewed.path("rules").has("award")).isFalse();
    assertThat(viewed.path("rulesHash").asString()).isEqualTo(hash);
    var job = successfulJob(player, 90);
    ok(player, "POST", "/leagues/" + id + "/submissions", leagueSubmission(viewed, job), 200);
    assertThat(db.queryForObject("SELECT rules FROM leagues WHERE id=?", String.class, id))
        .isEqualTo(original);
  }

  @Test
  void isolatesDraftsAndFreezesPublishedRules() throws Exception {
    var org = institution();
    var other = institution();
    var player = actor(null);
    assertThat(
            call(player, "POST", "/institution/leagues", leagueDraft(0, 2, 300000000)).statusCode())
        .isEqualTo(403);
    var l = ok(org, "POST", "/institution/leagues", leagueDraft(0, 2, 300000000), 200);
    String id = l.get("id").asString();
    assertThat(call(player, "GET", "/leagues/" + id, null).statusCode()).isEqualTo(404);
    assertThat(ok(other, "GET", "/institution/leagues", null, 200).toString()).doesNotContain(id);
    assertThat(
            call(other, "PUT", "/institution/leagues/" + id, leagueDraft(1, 2, 300000000))
                .statusCode())
        .isEqualTo(404);
    var edited = ok(org, "PUT", "/institution/leagues/" + id, leagueDraft(1, 3, 300000000), 200);
    assertThat(
            call(
                    org,
                    "POST",
                    "/institution/leagues/" + id + "/publish",
                    Map.of("revision", 1, "rulesHash", l.get("rulesHash").asString()))
                .statusCode())
        .isEqualTo(409);
    var pub =
        ok(
            org,
            "POST",
            "/institution/leagues/" + id + "/publish",
            Map.of("revision", 2, "rulesHash", edited.get("rulesHash").asString()),
            200);
    assertThat(pub.get("phase").asString()).isEqualTo("OPEN");
    assertThat(
            call(org, "PUT", "/institution/leagues/" + id, leagueDraft(3, 4, 300000000))
                .statusCode())
        .isEqualTo(409);
    var detail = ok(player, "GET", "/leagues/" + id, null, 200);
    assertThat(detail.get("league").get("rules").get("official").asBoolean()).isFalse();
    assertThat(detail.get("lab").get("modelHash").asString())
        .isEqualTo(NativeResearchFixtures.HASH);
    var rulesText =
        db.queryForObject(
            "SELECT rules FROM leagues WHERE id=?", String.class, UUID.fromString(id));
    assertThat(documentJson.hash(rulesText)).isEqualTo(pub.get("rulesHash").asString());
    ok(org, "POST", "/institution/leagues/" + id + "/cancel", Map.of("reason", "검증 목적 취소"), 200);
    assertThat(
            ok(player, "GET", "/leagues/" + id, null, 200)
                .get("league")
                .get("cancellationReason")
                .asString())
        .isEqualTo("검증 목적 취소");
  }

  @Test
  void ranksBestRecordsPreservesTiesAndSeparatesResearchConsent() throws Exception {
    var org = institution();
    var other = institution();
    var a = actor(null);
    var b = actor(null);
    var l = publishedLeague(org, 3, 300000000);
    String path = "/leagues/" + l.get("id").asString();
    var j1 = successfulJob(a, 90);
    var j2 = successfulJob(a, 80);
    var j3 = successfulJob(b, 80);
    ok(a, "POST", path + "/submissions", leagueSubmission(l, j1), 200);
    ok(a, "POST", path + "/submissions", leagueSubmission(l, j2), 200);
    ok(a, "POST", path + "/submissions", leagueSubmission(l, j2), 200);
    ok(b, "POST", path + "/submissions", leagueSubmission(l, j3), 200);
    var board = ok(a, "GET", path, null, 200).get("entries");
    assertThat(board.size()).isEqualTo(2);
    assertThat(board.get(0).get("score").decimalValue()).isEqualByComparingTo("20");
    assertThat(board.get(0).get("rank").asInt()).isEqualTo(1);
    assertThat(board.get(1).get("rank").asInt()).isEqualTo(1);
    assertThat(board.toString()).doesNotContain("jobId", "ownerId", "designNote");
    assertThat(ok(a, "GET", path + "/mine", null, 200).size()).isEqualTo(2);
    String jobId = j2.get("id").asString();
    assertThat(call(org, "GET", "/research/strategies/" + jobId, null).statusCode()).isEqualTo(404);
    UUID orgId =
        db.queryForObject("SELECT organization_id FROM accounts WHERE id=?", UUID.class, org.id());
    UUID otherId =
        db.queryForObject(
            "SELECT organization_id FROM accounts WHERE id=?", UUID.class, other.id());
    ok(a, "PUT", "/consents/" + orgId, Map.of("granted", true), 200);
    ok(a, "PUT", "/consents/" + otherId, Map.of("granted", true), 200);
    assertThat(
            ok(org, "GET", "/research/strategies/" + jobId, null, 200).get("leagueContexts").size())
        .isEqualTo(1);
    assertThat(
            ok(
                    org,
                    "GET",
                    "/research/strategies?modelHash=" + NativeResearchFixtures.HASH,
                    null,
                    200)
                .toString())
        .contains(jobId);
    assertThat(call(other, "GET", "/research/strategies/" + jobId, null).statusCode())
        .isEqualTo(404);
    ok(a, "PUT", "/consents/" + orgId, Map.of("granted", false), 200);
    assertThat(call(org, "GET", "/research/strategies/" + jobId, null).statusCode()).isEqualTo(404);
  }

  @Test
  void rejectsInvalidLeagueConditionsAndSerializesSubmissionLimit() throws Exception {
    var org = institution();
    var a = actor(null);
    var b = actor(null);
    var old = successfulJob(a, 90);
    var l = publishedLeague(org, 1, 300000000);
    String path = "/leagues/" + l.get("id").asString() + "/submissions";
    assertThat(call(a, "POST", path, leagueSubmission(l, old)).statusCode()).isEqualTo(422);
    var j1 = successfulJob(a, 90);
    var j2 = successfulJob(a, 80);
    assertThat(call(b, "POST", path, leagueSubmission(l, j1)).statusCode()).isEqualTo(404);
    assertThat(
            call(
                    a,
                    "POST",
                    path,
                    Map.of("jobId", j1.get("id").asString(), "rulesHash", "f".repeat(64)))
                .statusCode())
        .isEqualTo(422);
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var f1 = pool.submit(() -> call(a, "POST", path, leagueSubmission(l, j1)).statusCode());
      var f2 = pool.submit(() -> call(a, "POST", path, leagueSubmission(l, j2)).statusCode());
      assertThat(List.of(f1.get(), f2.get())).containsExactlyInAnyOrder(200, 409);
    }
    var cheap = publishedLeague(org, 3, 1);
    var job = successfulJob(a, 90);
    assertThat(
            call(
                    a,
                    "POST",
                    "/leagues/" + cheap.get("id").asString() + "/submissions",
                    leagueSubmission(cheap, job))
                .statusCode())
        .isEqualTo(422);
    var closed = publishedLeague(org, 3, 300000000);
    var late = successfulJob(a, 90);
    db.update(
        "UPDATE leagues SET opens_at=?,closes_at=? WHERE id=?",
        java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(60)),
        java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(1)),
        UUID.fromString(closed.get("id").asString()));
    assertThat(
            call(
                    a,
                    "POST",
                    "/leagues/" + closed.get("id").asString() + "/submissions",
                    leagueSubmission(closed, late))
                .statusCode())
        .isEqualTo(409);
  }

  @Test
  void rejectsChangedEngineAndUnavailableOrganization() throws Exception {
    var org = institution();
    var a = actor(null);
    var l = publishedLeague(org, 3, 300000000);
    String path = "/leagues/" + l.get("id").asString() + "/submissions";
    var first = successfulJob(a, 90);
    ok(a, "POST", path, leagueSubmission(l, first), 200);
    var changed = successfulJob(a, 80);
    UUID id = UUID.fromString(changed.get("id").asString());
    var result =
        (tools.jackson.databind.node.ObjectNode)
            json.readTree(
                db.queryForObject(
                    "SELECT result FROM simulation_jobs WHERE id=?", String.class, id));
    ((tools.jackson.databind.node.ObjectNode) result.get("engine"))
        .put("binarySha256", "b".repeat(64));
    db.update(
        "UPDATE simulation_jobs SET result=? WHERE id=?", json.writeValueAsString(result), id);
    assertThat(call(a, "POST", path, leagueSubmission(l, changed)).statusCode()).isEqualTo(422);
    UUID orgId =
        db.queryForObject("SELECT organization_id FROM accounts WHERE id=?", UUID.class, org.id());
    db.update("UPDATE organizations SET approved=false WHERE id=?", orgId);
    assertThat(call(a, "GET", "/leagues/" + l.get("id").asString(), null).statusCode())
        .isEqualTo(404);
    assertThat(call(a, "POST", path, leagueSubmission(l, changed)).statusCode()).isEqualTo(404);
    assertThat(call(org, "GET", "/institution/leagues", null).statusCode()).isEqualTo(403);
  }

  @Test
  void separatesSingleAdminFromMembersAndEnforcesApprovalAndMfaEnrollment() throws Exception {
    var member = actor(null);
    var adminId = UUID.randomUUID();
    String adminName = "admin_" + adminId.toString().substring(0, 8);
    accounts.add(
        new Account(
            adminId,
            adminName,
            "관리자 시험",
            passwords.encode("test-password-1234"),
            "ADMIN",
            null,
            "APPROVED",
            null,
            "",
            "",
            true));
    String secret = mfa.provision(adminId);
    var admin =
        new Actor(
            adminId,
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    ok(
        admin,
        "POST",
        "/auth/login",
        Map.of(
            "username", adminName, "password", "test-password-1234", "otp", MfaTests.otp(secret)),
        200);
    assertThat(call(admin, "GET", "/research/strategies", null).statusCode()).isEqualTo(403);
    assertThat(
            call(admin, "POST", "/institution/leagues", leagueDraft(0, 2, 300000000)).statusCode())
        .isEqualTo(403);
    assertThat(call(member, "GET", "/admin/members", null).statusCode()).isEqualTo(403);
    assertThatThrownBy(
            () ->
                accounts.add(
                    new Account(
                        UUID.randomUUID(),
                        "admin_second",
                        "관리자 중복",
                        passwords.encode("test-password-1234"),
                        "ADMIN",
                        null,
                        "APPROVED",
                        null,
                        "",
                        "",
                        true)))
        .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
    var applicant =
        new Actor(
            UUID.randomUUID(),
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    String username = "biz_" + UUID.randomUUID().toString().substring(0, 8);
    var registration =
        Map.of(
            "username",
            username,
            "password",
            "test-password-1234",
            "memberType",
            "BUSINESS",
            "organizationName",
            "가입 검토 시험 기업",
            "purpose",
            "빗물 설계 연구",
            "districtId",
            "11680",
            "affiliationType",
            "AFFILIATED");
    var pending = ok(applicant, "POST", "/auth/register", registration, 200);
    assertThat(pending.get("role").asString()).isEqualTo("MEMBER");
    assertThat(pending.get("approvalStatus").asString()).isEqualTo("PENDING");
    assertThat(call(applicant, "GET", "/auth/me", null).statusCode()).isEqualTo(401);
    var credentials = Map.of("username", username, "password", "test-password-1234");
    assertThat(call(applicant, "POST", "/auth/login", credentials).statusCode()).isEqualTo(403);
    assertThat(call(applicant, "POST", "/auth/mfa/enrollment", credentials).statusCode())
        .isEqualTo(403);
    String id = pending.get("id").asString(), path = "/admin/members/" + id + "/reviews";
    assertThat(ok(admin, "GET", "/admin/members", null, 200).toString())
        .contains(id, "가입 검토 시험 기업")
        .doesNotContain("password_hash", "encrypted_secret");
    assertThat(call(admin, "GET", "/admin/members?status=INVALID", null).statusCode())
        .isEqualTo(400);
    assertThat(
            call(
                    member,
                    "POST",
                    path,
                    Map.of("decision", "APPROVE", "expectedStatus", "PENDING", "reason", "위조 승인"))
                .statusCode())
        .isEqualTo(403);
    ok(
        admin,
        "POST",
        path,
        Map.of("decision", "REJECT", "expectedStatus", "PENDING", "reason", "소속 확인 자료 보완"),
        200);
    assertThat(call(applicant, "POST", "/auth/login", credentials).statusCode()).isEqualTo(403);
    assertThat(
            call(
                    admin,
                    "POST",
                    path,
                    Map.of(
                        "decision", "APPROVE", "expectedStatus", "PENDING", "reason", "이전 상태 충돌"))
                .statusCode())
        .isEqualTo(409);
    ok(
        admin,
        "POST",
        path,
        Map.of("decision", "APPROVE", "expectedStatus", "REJECTED", "reason", "소속 및 이용 목적 확인"),
        200);
    assertThat(ok(admin, "GET", path, null, 200).size()).isEqualTo(2);
    var blocked = call(applicant, "POST", "/auth/login", credentials);
    assertThat(blocked.statusCode()).isEqualTo(403);
    assertThat(blocked.body()).contains("MFA_ENROLLMENT_REQUIRED");
    var enrollment = ok(applicant, "POST", "/auth/mfa/enrollment", credentials, 200);
    assertThat(call(applicant, "GET", "/research/strategies", null).statusCode()).isEqualTo(401);
    String code = MfaTests.otp(enrollment.get("secret").asString());
    var approved = ok(applicant, "POST", "/auth/mfa/confirm", Map.of("otp", code), 200);
    assertThat(approved.get("memberType").asString()).isEqualTo("BUSINESS");
    ok(applicant, "GET", "/research/strategies", null, 200);
    assertThat(call(applicant, "GET", "/admin/members", null).statusCode()).isEqualTo(403);
    assertThat(call(applicant, "POST", "/auth/mfa/enrollment", credentials).statusCode())
        .isEqualTo(409);
    assertThat(
            call(
                    applicant,
                    "POST",
                    "/auth/login",
                    Map.of("username", username, "password", "test-password-1234", "otp", code))
                .statusCode())
        .isEqualTo(401);
    ok(
        admin,
        "POST",
        path,
        Map.of("decision", "SUSPEND", "expectedStatus", "APPROVED", "reason", "검토 중 접근 중지"),
        200);
    assertThat(call(applicant, "GET", "/research/strategies", null).statusCode()).isEqualTo(401);
    assertThat(call(applicant, "POST", "/auth/login", credentials).statusCode()).isEqualTo(403);
    assertThat(
            call(
                    admin,
                    "POST",
                    "/admin/members/" + adminId + "/reviews",
                    Map.of(
                        "decision", "SUSPEND", "expectedStatus", "APPROVED", "reason", "자기 권한 변경"))
                .statusCode())
        .isEqualTo(403);
  }
}
