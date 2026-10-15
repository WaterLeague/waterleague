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
        "spring.datasource.url=jdbc:h2:mem:participation;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@ActiveProfiles("local")
class LeagueParticipationWorkflowTests {
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
        model.hash(),
        "placements",
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 40)),
        "designNote",
        note,
        "baseRevision",
        revision);
  }

  Map<String, Object> leagueDraft(int revision, int limit, long budget) {
    return Map.of(
        "modelHash",
        model.hash(),
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

  Map<String, Object> leagueSubmission(JsonNode league, JsonNode job) {
    return Map.of(
        "jobId", job.get("id").asString(), "rulesHash", league.get("rulesHash").asString());
  }

  JsonNode league(Actor org, String access, String admission, boolean team, int limit, int size)
      throws Exception {
    var d = new HashMap<>(leagueDraft(0, limit, 300000000));
    var p = new HashMap<String, Object>();
    p.put("access", access);
    p.put("admission", admission);
    p.put("entryMode", team ? "TEAM" : "INDIVIDUAL");
    if (team) p.put("teamSizeLimit", size);
    d.put("participation", p);
    var l = ok(org, "POST", "/institution/leagues", d, 200);
    return ok(
        org,
        "POST",
        "/institution/leagues/" + l.path("id").asString() + "/publish",
        Map.of("revision", 1, "rulesHash", l.path("rulesHash").asString()),
        200);
  }

  String path(JsonNode l) {
    return "/leagues/" + l.path("id").asString();
  }

  String manage(JsonNode l) {
    return "/institution" + path(l);
  }

  JsonNode join(Actor a, JsonNode l, String code) throws Exception {
    var d = new HashMap<String, Object>();
    d.put("rulesHash", l.path("rulesHash").asString());
    if (code != null) d.put("code", code);
    return ok(a, "POST", path(l) + "/participation", d, 200);
  }

  JsonNode decision(Actor org, Actor a, JsonNode l, int rev, String state) throws Exception {
    return ok(
        org,
        "POST",
        manage(l) + "/participants/" + a.id() + "/decisions",
        Map.of("revision", rev, "state", state, "reason", "참가 자격 검토"),
        200);
  }

  JsonNode team(Actor a, JsonNode l, String name) throws Exception {
    return ok(a, "POST", path(l) + "/teams", Map.of("name", name), 200);
  }

  Map<String, Object> teamJoin(JsonNode l, JsonNode t) {
    return Map.of(
        "code",
        t.path("code").asString(),
        "teamId",
        t.path("team").path("id").asString(),
        "rulesHash",
        l.path("rulesHash").asString());
  }

  @Test
  void protectsPrivateDiscoveryRotatesTokensAndRequiresAdmission() throws Exception {
    var org = institution();
    var other = institution();
    var a = actor(null);
    var b = actor(null);
    var l = league(org, "INVITE", "APPROVAL", false, 3, 0);
    var id = UUID.fromString(l.path("id").asString());
    assertThat(l.path("rules").path("schemaVersion").asInt()).isEqualTo(3);
    assertThat(call(a, "GET", "/leagues", null).body()).doesNotContain(id.toString());
    assertThat(call(a, "GET", path(l), null).statusCode()).isEqualTo(404);
    assertThat(call(other, "GET", path(l), null).statusCode()).isEqualTo(404);
    var guest = new Actor(UUID.randomUUID(), HttpClient.newHttpClient());
    assertThat(call(guest, "GET", "/leagues/joined", null).statusCode()).isEqualTo(401);
    assertThat(call(guest, "GET", path(l), null).statusCode()).isEqualTo(404);
    assertThat(call(other, "POST", manage(l) + "/invitation", Map.of()).statusCode())
        .isEqualTo(404);
    var response = call(org, "POST", manage(l) + "/invitation", Map.of());
    assertThat(response.headers().firstValue("cache-control").orElse("")).contains("no-store");
    String code = json.readTree(response.body()).path("code").asString();
    assertThat(code).hasSize(43);
    assertThat(
            db.queryForObject(
                "SELECT token_hash FROM league_invitations WHERE league_id=?", String.class, id))
        .doesNotContain(code)
        .hasSize(64);
    assertThat(ok(a, "POST", "/leagues/invitations/preview", Map.of("code", code), 200).path("id"))
        .isEqualTo(l.path("id"));
    var p = join(a, l, code).path("participant");
    assertThat(p.path("state").asString()).isEqualTo("PENDING");
    assertThat(ok(a, "GET", path(l), null, 200).path("boardVisible").asBoolean()).isFalse();
    assertThat(ok(a, "GET", "/leagues/joined", null, 200).toString()).contains(id.toString());
    var job = successfulJob(a, 90);
    assertThat(call(a, "POST", path(l) + "/submissions", leagueSubmission(l, job)).statusCode())
        .isEqualTo(409);
    String rotated =
        ok(org, "POST", manage(l) + "/invitation", Map.of(), 200).path("code").asString();
    assertThat(call(b, "POST", "/leagues/invitations/preview", Map.of("code", code)).statusCode())
        .isEqualTo(404);
    decision(org, a, l, 1, "APPROVED");
    ok(a, "POST", path(l) + "/submissions", leagueSubmission(l, job), 200);
    assertThat(ok(a, "GET", path(l), null, 200).path("entries").size()).isEqualTo(1);
    join(b, l, rotated);
    assertThat(ok(b, "GET", path(l), null, 200).path("entries").isEmpty()).isTrue();
    ok(org, "DELETE", manage(l) + "/invitation", Map.of(), 200);
    assertThat(
            call(b, "POST", "/leagues/invitations/preview", Map.of("code", rotated)).statusCode())
        .isEqualTo(404);
    String expired =
        ok(org, "POST", manage(l) + "/invitation", Map.of(), 200).path("code").asString();
    db.update(
        "UPDATE league_invitations SET expires_at=? WHERE league_id=?",
        java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(1)),
        id);
    assertThat(
            call(b, "POST", "/leagues/invitations/preview", Map.of("code", expired)).statusCode())
        .isEqualTo(404);
    assertThat(call(a, "GET", path(l), null).statusCode()).isEqualTo(200);
  }

  @Test
  void preservesReviewHistoryRevisionAndSubmissionQuotaAfterReentry() throws Exception {
    var org = institution();
    var a = actor(null);
    var l = league(org, "PUBLIC", "APPROVAL", false, 1, 0);
    join(a, l, null);
    decision(org, a, l, 1, "REJECTED");
    assertThat(
            call(
                    org,
                    "POST",
                    manage(l) + "/participants/" + a.id() + "/decisions",
                    Map.of("revision", 1, "state", "APPROVED", "reason", "오래된 화면"))
                .statusCode())
        .isEqualTo(409);
    assertThat(join(a, l, null).path("participant").path("revision").asInt()).isEqualTo(3);
    decision(org, a, l, 3, "APPROVED");
    var job = successfulJob(a, 90);
    ok(a, "POST", path(l) + "/submissions", leagueSubmission(l, job), 200);
    ok(a, "POST", path(l) + "/participation/withdraw", Map.of("revision", 4), 200);
    assertThat(ok(a, "GET", path(l), null, 200).path("entries").size()).isZero();
    join(a, l, null);
    decision(org, a, l, 6, "APPROVED");
    var second = successfulJob(a, 80);
    assertThat(call(a, "POST", path(l) + "/submissions", leagueSubmission(l, second)).statusCode())
        .isEqualTo(409);
    assertThat(ok(a, "GET", path(l) + "/participation", null, 200).path("submissionCount").asInt())
        .isEqualTo(1);
    assertThat(ok(org, "GET", manage(l) + "/participants/" + a.id() + "/events", null, 200).size())
        .isEqualTo(7);
    assertThat(
            call(org, "GET", "/research/strategies/" + job.path("id").asString(), null)
                .statusCode())
        .isEqualTo(404);
    assertThat(
            call(
                    a,
                    "POST",
                    manage(l) + "/participants/" + a.id() + "/decisions",
                    Map.of("revision", 7, "state", "APPROVED", "reason", "승인 시도"))
                .statusCode())
        .isEqualTo(403);
  }

  @Test
  void serializesLastTeamSlotAndSeparatesInvitationPurposes() throws Exception {
    var org = institution();
    var a = actor(null);
    var b = actor(null);
    var c = actor(null);
    var l = league(org, "INVITE", "OPEN", true, 3, 2);
    String code = ok(org, "POST", manage(l) + "/invitation", Map.of(), 200).path("code").asString();
    for (var p : List.of(a, b, c)) join(p, l, code);
    var t = team(a, l, "성수 연구팀");
    String teamCode = t.path("code").asString();
    assertThat(
            call(b, "POST", "/leagues/invitations/preview", Map.of("code", teamCode)).statusCode())
        .isEqualTo(404);
    assertThat(call(b, "POST", path(l) + "/teams/preview", Map.of("code", code)).statusCode())
        .isEqualTo(404);
    assertThat(
            ok(b, "POST", path(l) + "/teams/preview", Map.of("code", teamCode), 200)
                .path("name")
                .asString())
        .isEqualTo("성수 연구팀");
    int first, second;
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var f =
          pool.submit(() -> call(b, "POST", path(l) + "/teams/join", teamJoin(l, t)).statusCode());
      var g =
          pool.submit(() -> call(c, "POST", path(l) + "/teams/join", teamJoin(l, t)).statusCode());
      first = f.get();
      second = g.get();
    }
    assertThat(List.of(first, second)).containsExactlyInAnyOrder(200, 409);
    assertThat(
            ok(a, "GET", path(l) + "/participation", null, 200).path("team").path("members").size())
        .isEqualTo(2);
    assertThat(call(a, "POST", path(l) + "/teams/leave", Map.of()).statusCode()).isEqualTo(409);
    var member = first == 200 ? b : c;
    assertThat(call(member, "POST", path(l) + "/teams/invitation", Map.of()).statusCode())
        .isEqualTo(404);
    ok(member, "POST", path(l) + "/teams/leave", Map.of(), 200);
    ok(a, "DELETE", path(l) + "/teams/invitation", Map.of(), 200);
    assertThat(call(b, "POST", path(l) + "/teams/preview", Map.of("code", teamCode)).statusCode())
        .isEqualTo(404);
    ok(a, "POST", path(l) + "/teams/leave", Map.of(), 200);
    assertThat(ok(a, "GET", path(l) + "/participation", null, 200).path("team").isNull()).isTrue();
  }

  @Test
  void sharesTeamQuotaFreezesRosterAndBlocksIneligibleMembers() throws Exception {
    var org = institution();
    var a = actor(null);
    var b = actor(null);
    var c = actor(null);
    var l = league(org, "PUBLIC", "OPEN", true, 1, 3);
    for (var p : List.of(a, b, c)) join(p, l, null);
    var t = team(a, l, "합동 설계팀");
    ok(b, "POST", path(l) + "/teams/join", teamJoin(l, t), 200);
    var ja = successfulJob(a, 90);
    var jb = successfulJob(b, 80);
    assertThat(call(b, "POST", path(l) + "/submissions", leagueSubmission(l, ja)).statusCode())
        .isEqualTo(404);
    assertThat(
            ok(a, "GET", path(l) + "/participation", null, 200)
                .path("team")
                .path("frozenAt")
                .isNull())
        .isTrue();
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var f =
          pool.submit(
              () ->
                  call(a, "POST", path(l) + "/submissions", leagueSubmission(l, ja)).statusCode());
      var g =
          pool.submit(
              () ->
                  call(b, "POST", path(l) + "/submissions", leagueSubmission(l, jb)).statusCode());
      assertThat(List.of(f.get(), g.get())).containsExactlyInAnyOrder(200, 409);
    }
    var state = ok(a, "GET", path(l) + "/participation", null, 200);
    assertThat(state.path("submissionCount").asInt()).isEqualTo(1);
    assertThat(state.path("team").path("frozenAt").isTextual()).isTrue();
    assertThat(state.toString())
        .doesNotContain(ja.path("id").asString(), jb.path("id").asString(), "designNote");
    assertThat(call(b, "POST", path(l) + "/teams/leave", Map.of()).statusCode()).isEqualTo(409);
    assertThat(call(c, "POST", path(l) + "/teams/join", teamJoin(l, t)).statusCode())
        .isEqualTo(404);
    assertThat(
            ok(a, "GET", path(l), null, 200).path("entries").get(0).path("displayName").asString())
        .isEqualTo("합동 설계팀");
    db.update("UPDATE accounts SET enabled=false WHERE id=?", b.id());
    assertThat(ok(a, "GET", path(l), null, 200).path("entries").size()).isZero();
    assertThat(call(a, "POST", path(l) + "/submissions", leagueSubmission(l, ja)).statusCode())
        .isEqualTo(409);
    db.update("UPDATE accounts SET enabled=true WHERE id=?", b.id());
    ok(b, "POST", path(l) + "/participation/withdraw", Map.of("revision", 1), 200);
    assertThat(ok(a, "GET", path(l), null, 200).path("entries").size()).isZero();
    join(b, l, null);
    assertThat(ok(a, "GET", path(l), null, 200).path("entries").size()).isEqualTo(1);
    assertThat(ok(b, "GET", path(l) + "/participation", null, 200).path("submissionCount").asInt())
        .isEqualTo(1);
    assertThat(call(b, "GET", "/simulations/" + ja.path("id").asString(), null).statusCode())
        .isEqualTo(404);
  }

  @Test
  void ranksBestTeamEntryAndPreservesIndividualResearchConsent() throws Exception {
    var org = institution();
    var other = institution();
    var a = actor(null);
    var b = actor(null);
    var c = actor(null);
    var l = league(org, "PUBLIC", "OPEN", true, 3, 3);
    for (var p : List.of(a, b, c)) join(p, l, null);
    var t = team(a, l, "공동 후보");
    ok(b, "POST", path(l) + "/teams/join", teamJoin(l, t), 200);
    team(c, l, "비교 후보");
    var ja = successfulJob(a, 90);
    var jb = successfulJob(b, 80);
    var jc = successfulJob(c, 80);
    ok(a, "POST", path(l) + "/submissions", leagueSubmission(l, ja), 200);
    ok(b, "POST", path(l) + "/submissions", leagueSubmission(l, jb), 200);
    ok(b, "POST", path(l) + "/submissions", leagueSubmission(l, jb), 200);
    ok(c, "POST", path(l) + "/submissions", leagueSubmission(l, jc), 200);
    var board = ok(a, "GET", path(l), null, 200).path("entries");
    assertThat(board.size()).isEqualTo(2);
    assertThat(board.get(0).path("rank").asInt()).isEqualTo(1);
    assertThat(board.get(1).path("rank").asInt()).isEqualTo(1);
    assertThat(ok(a, "GET", path(l) + "/mine", null, 200).size()).isEqualTo(1);
    var oid = accounts.byId(org.id()).orElseThrow().organizationId();
    ok(a, "PUT", "/consents/" + oid, Map.of("granted", true), 200);
    assertThat(
            call(org, "GET", "/research/strategies/" + ja.path("id").asString(), null).statusCode())
        .isEqualTo(200);
    assertThat(
            call(org, "GET", "/research/strategies/" + jb.path("id").asString(), null).statusCode())
        .isEqualTo(404);
    var privateLeague = league(other, "INVITE", "OPEN", false, 3, 0);
    String invite =
        ok(other, "POST", manage(privateLeague) + "/invitation", Map.of(), 200)
            .path("code")
            .asString();
    join(a, privateLeague, invite);
    var fresh = successfulJob(a, 90);
    ok(a, "POST", path(l) + "/submissions", leagueSubmission(l, fresh), 200);
    ok(
        a,
        "POST",
        path(privateLeague) + "/submissions",
        leagueSubmission(privateLeague, fresh),
        200);
    String contexts =
        ok(org, "GET", "/research/strategies/" + fresh.path("id").asString(), null, 200)
            .path("leagueContexts")
            .toString();
    assertThat(contexts)
        .contains(l.path("id").asString())
        .doesNotContain(privateLeague.path("id").asString());
    assertThat(
            ok(org, "GET", "/research/strategies/" + fresh.path("id").asString(), null, 200)
                .path("leagueContexts")
                .get(0)
                .path("teamName")
                .asString())
        .isEqualTo("공동 후보");
    UUID jobId = UUID.fromString(fresh.path("id").asString()), token = UUID.randomUUID();
    var stored =
        (tools.jackson.databind.node.ObjectNode)
            json.readTree(
                db.queryForObject(
                    "SELECT result FROM simulation_jobs WHERE id=?", String.class, jobId));
    stored.put("artifactToken", token.toString());
    db.update(
        "UPDATE simulation_jobs SET result=? WHERE id=?", json.writeValueAsString(stored), jobId);
    var directory = java.nio.file.Path.of(artifactRoot, jobId.toString(), token.toString());
    java.nio.file.Files.createDirectories(directory);
    try {
      // 파일 전송의 권한 범위 시험이며 수문 산출물 검증과 구분한다.
      var files =
          new ArrayList<>(
              List.of(
                  "manifest.json",
                  "builder.py",
                  "model-source.json",
                  "model.json",
                  "placements.json",
                  "request.json",
                  "result.json"));
      for (var scenario : List.of("baseline", "strategy", "low", "high"))
        for (var ext : List.of("inp", "rpt", "out")) files.add(scenario + "." + ext);
      for (String file : files)
        java.nio.file.Files.writeString(directory.resolve(file), "권한 시험용 파일");
      String orgHistory =
          bundleHistory(org, "/research/strategies/" + jobId + "/bundle")
              .path("leagueContexts")
              .toString();
      assertThat(orgHistory)
          .contains(l.path("id").asString())
          .doesNotContain(privateLeague.path("id").asString());
      assertThat(
              bundleHistory(a, "/simulations/" + jobId + "/bundle").path("leagueContexts").size())
          .isEqualTo(2);
    } finally {
      try (var paths = java.nio.file.Files.walk(directory.getParent())) {
        for (var file : paths.sorted(java.util.Comparator.reverseOrder()).toList())
          java.nio.file.Files.delete(file);
      }
    }

    var otherId = accounts.byId(other.id()).orElseThrow().organizationId();
    ok(a, "PUT", "/consents/" + otherId, Map.of("granted", true), 200);
    assertThat(
            ok(other, "GET", "/research/strategies/" + fresh.path("id").asString(), null, 200)
                .path("leagueContexts")
                .size())
        .isEqualTo(2);
  }

  JsonNode bundleHistory(Actor a, String endpoint) throws Exception {
    var response =
        a.client()
            .send(
                HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/api/v1" + endpoint))
                    .build(),
                HttpResponse.BodyHandlers.ofByteArray());
    assertThat(response.statusCode()).isEqualTo(200);
    try (var zip =
        new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(response.body()))) {
      java.util.zip.ZipEntry entry;
      while ((entry = zip.getNextEntry()) != null)
        if (entry.getName().equals("strategy-history.json"))
          return json.readTree(zip.readAllBytes());
    }
    throw new AssertionError("이력 파일 누락");
  }

  @Test
  void rejectsInvalidRulesAndDisablesPrivateActionsAfterCancellation() throws Exception {
    var org = institution();
    var a = actor(null);
    for (var p :
        List.of(
            Map.of("access", "PUBLIC", "admission", "OPEN", "entryMode", "TEAM"),
            Map.of(
                "access",
                "INVITE",
                "admission",
                "OPEN",
                "entryMode",
                "INDIVIDUAL",
                "teamSizeLimit",
                2),
            Map.of(
                "access",
                "PUBLIC",
                "admission",
                "OPEN",
                "entryMode",
                "TEAM",
                "teamSizeLimit",
                11))) {
      var d = new HashMap<>(leagueDraft(0, 3, 300000000));
      d.put("participation", p);
      assertThat(call(org, "POST", "/institution/leagues", d).statusCode()).isEqualTo(400);
    }
    var l = league(org, "INVITE", "OPEN", false, 3, 0);
    String code = ok(org, "POST", manage(l) + "/invitation", Map.of(), 200).path("code").asString();
    join(a, l, code);
    ok(org, "POST", manage(l) + "/cancel", Map.of("reason", "접수 취소"), 200);
    assertThat(call(a, "POST", "/leagues/invitations/preview", Map.of("code", code)).statusCode())
        .isEqualTo(409);
    assertThat(call(org, "POST", manage(l) + "/invitation", Map.of()).statusCode()).isEqualTo(409);
    ok(a, "POST", path(l) + "/participation/withdraw", Map.of("revision", 1), 200);
    assertThat(call(a, "GET", path(l), null).statusCode()).isEqualTo(404);
    var oid = accounts.byId(org.id()).orElseThrow().organizationId();
    db.update("UPDATE organizations SET approved=false WHERE id=?", oid);
    assertThat(call(a, "GET", path(l) + "/participation", null).statusCode()).isEqualTo(404);
    assertThat(call(org, "GET", manage(l) + "/participants", null).statusCode()).isEqualTo(404);
  }

  @Test
  void paginatesParticipantsAndRejectsMissingMfaAndCsrf() throws Exception {
    var org = institution();
    var l = league(org, "PUBLIC", "OPEN", false, 2, 0);
    UUID id = UUID.fromString(l.path("id").asString());
    String password = passwords.encode("test-password-1234");
    for (int i = 0; i < 103; i++) {
      UUID owner = UUID.randomUUID();
      accounts.add(
          new Account(
              owner,
              "page_" + owner.toString().substring(0, 8),
              "참가자 " + i,
              password,
              "MEMBER",
              "PLAYER",
              "APPROVED",
              null,
              "",
              "",
              true));
      db.update(
          "INSERT INTO"
              + " league_participants(league_id,owner_id,state,revision,rules_hash,created_at,updated_at)"
              + " VALUES(?,?,'APPROVED',1,?,?,?)",
          id,
          owner,
          l.path("rulesHash").asString(),
          java.sql.Timestamp.from(java.time.Instant.now()),
          java.sql.Timestamp.from(java.time.Instant.now()));
    }
    var first = ok(org, "GET", manage(l) + "/participants", null, 200);
    assertThat(first.path("items").size()).isEqualTo(100);
    var second =
        ok(
            org,
            "GET",
            manage(l) + "/participants?after=" + first.path("nextCursor").asString(),
            null,
            200);
    assertThat(second.path("items").size()).isEqualTo(3);
    assertThat(second.path("nextCursor").isNull()).isTrue();
    var seen = new HashSet<String>();
    for (var page : List.of(first, second))
      for (var row : page.path("items"))
        assertThat(seen.add(row.path("ownerId").asString())).isTrue();
    var a = actor(null);
    var noCsrf =
        a.client()
            .send(
                HttpRequest.newBuilder(
                        URI.create(
                            "http://127.0.0.1:" + port + "/api/v1" + path(l) + "/participation"))
                    .header("Content-Type", "application/json")
                    .POST(
                        HttpRequest.BodyPublishers.ofString(
                            json.writeValueAsString(
                                Map.of("rulesHash", l.path("rulesHash").asString()))))
                    .build(),
                HttpResponse.BodyHandlers.ofString());
    assertThat(noCsrf.statusCode()).isEqualTo(403);
    var orgAccount = accounts.byId(org.id()).orElseThrow();
    var guest =
        new Actor(
            UUID.randomUUID(),
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    assertThat(
            call(
                    guest,
                    "POST",
                    "/auth/login",
                    Map.of("username", orgAccount.username(), "password", "test-password-1234"))
                .statusCode())
        .isEqualTo(401);
    assertThat(call(guest, "GET", manage(l) + "/participants", null).statusCode()).isEqualTo(401);
  }

  @Test
  void serializesApprovalRevocationAgainstSubmission() throws Exception {
    var org = institution();
    var a = actor(null);
    var l = league(org, "PUBLIC", "APPROVAL", false, 2, 0);
    join(a, l, null);
    decision(org, a, l, 1, "APPROVED");
    int revision;
    if (Boolean.TRUE.equals(
        db.execute(
            (org.springframework.jdbc.core.ConnectionCallback<Boolean>)
                connection ->
                    connection.getMetaData().getDatabaseProductName().equals("PostgreSQL")))) {
      try (var pool = java.util.concurrent.Executors.newSingleThreadExecutor()) {
        new org.springframework.transaction.support.TransactionTemplate(transactions)
            .executeWithoutResult(
                status -> {
                  research.ownerLock(a.id());
                  var result = pool.submit(() -> decision(org, a, l, 2, "REJECTED"));
                  try {
                    assertThat(
                            result
                                .get(5, java.util.concurrent.TimeUnit.SECONDS)
                                .path("state")
                                .asString())
                        .isEqualTo("REJECTED");
                  } catch (Exception e) {
                    throw new AssertionError("회원 잠금 중 외래키 확인 차단", e);
                  }
                });
      }
      join(a, l, null);
      decision(org, a, l, 4, "APPROVED");
      revision = 5;
    } else revision = 2;
    var job = successfulJob(a, 90);
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var submit =
          pool.submit(
              () ->
                  call(a, "POST", path(l) + "/submissions", leagueSubmission(l, job)).statusCode());
      var reject =
          pool.submit(
              () ->
                  call(
                          org,
                          "POST",
                          manage(l) + "/participants/" + a.id() + "/decisions",
                          Map.of("revision", revision, "state", "REJECTED", "reason", "참가 자격 변경"))
                      .statusCode());
      assertThat(reject.get()).isEqualTo(200);
      assertThat(submit.get()).isIn(200, 409);
    }
    assertThat(ok(a, "GET", path(l), null, 200).path("entries").size()).isZero();
    assertThat(call(a, "POST", path(l) + "/submissions", leagueSubmission(l, job)).statusCode())
        .isEqualTo(409);
  }

  @Test
  void freezesConcurrentTeamJoinAndRejectsCrossLeagueCodeAndHash() throws Exception {
    var org = institution();
    var a = actor(null);
    var b = actor(null);
    var l = league(org, "INVITE", "OPEN", true, 2, 2);
    var other = league(org, "INVITE", "OPEN", false, 2, 0);
    String code = ok(org, "POST", manage(l) + "/invitation", Map.of(), 200).path("code").asString();
    assertThat(
            call(
                    a,
                    "POST",
                    path(other) + "/participation",
                    Map.of("rulesHash", other.path("rulesHash").asString(), "code", code))
                .statusCode())
        .isEqualTo(404);
    assertThat(
            call(
                    a,
                    "POST",
                    path(l) + "/participation",
                    Map.of("rulesHash", "f".repeat(64), "code", code))
                .statusCode())
        .isEqualTo(422);
    join(a, l, code);
    join(b, l, code);
    var t = team(a, l, "구성 경합");
    var job = successfulJob(a, 90);
    int joined;
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
      var submit =
          pool.submit(
              () ->
                  call(a, "POST", path(l) + "/submissions", leagueSubmission(l, job)).statusCode());
      var enter =
          pool.submit(() -> call(b, "POST", path(l) + "/teams/join", teamJoin(l, t)).statusCode());
      assertThat(submit.get()).isEqualTo(200);
      joined = enter.get();
      assertThat(joined).isIn(200, 404);
    }
    var state = ok(a, "GET", path(l) + "/participation", null, 200).path("team");
    assertThat(state.path("frozenAt").isTextual()).isTrue();
    assertThat(state.path("members").size()).isEqualTo(joined == 200 ? 2 : 1);
    assertThat(call(b, "POST", path(l) + "/teams/join", teamJoin(l, t)).statusCode())
        .isEqualTo(404);
  }

  @Test
  void keepsOrganizerRejectionAcrossOpenLeagueReapplications() throws Exception {
    var org = institution();
    var a = actor(null);
    var l = league(org, "PUBLIC", "OPEN", false, 2, 0);
    join(a, l, null);
    decision(org, a, l, 1, "REJECTED");
    var first = join(a, l, null).path("participant");
    assertThat(first.path("state").asString()).isEqualTo("PENDING");
    assertThat(first.path("reviewRequired").asBoolean()).isTrue();
    ok(a, "POST", path(l) + "/participation/withdraw", Map.of("revision", 3), 200);
    assertThat(join(a, l, null).path("participant").path("state").asString()).isEqualTo("PENDING");
    var job = successfulJob(a, 90);
    assertThat(call(a, "POST", path(l) + "/submissions", leagueSubmission(l, job)).statusCode())
        .isEqualTo(409);
    assertThat(decision(org, a, l, 5, "APPROVED").path("reviewRequired").asBoolean()).isFalse();
    ok(a, "POST", path(l) + "/submissions", leagueSubmission(l, job), 200);
  }
}
