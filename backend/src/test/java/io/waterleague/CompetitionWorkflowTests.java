package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.model.service.LabModelService;
import java.math.BigDecimal;
import java.net.*;
import java.net.http.*;
import java.sql.Timestamp;
import java.time.*;
import java.time.temporal.ChronoUnit;
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
class CompetitionWorkflowTests extends PostgresIntegrationTest {
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
    db.execute("TRUNCATE accounts, organizations, spring_session, rate_limits CASCADE");
  }

  Actor actor(UUID org) throws Exception {
    return actor(org, false);
  }

  Actor actor(UUID org, boolean admin) throws Exception {
    UUID id = UUID.randomUUID();
    String name = "qa_" + id.toString().substring(0, 8);
    accounts.add(
        new Account(
            id,
            name,
            name,
            passwords.encode("test-password-1234"),
            admin ? "ADMIN" : "MEMBER",
            admin ? null : org == null ? "PLAYER" : "INSTITUTION",
            "APPROVED",
            org,
            "",
            "",
            true,
            "11680",
            "AFFILIATED"));
    String secret = org == null && !admin ? null : mfa.provision(id);
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

  @Autowired io.waterleague.evaluation.service.ScorePolicyService policy;
  @Autowired io.waterleague.disaster.service.DisasterService disasters;
  @Autowired io.waterleague.competition.repository.CompetitionRepository competitionRepo;
  @Autowired io.waterleague.common.service.JsonService canonical;

  Actor host() throws Exception {
    var org = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", org, "대회 시험 기관");
    return actor(org);
  }

  Map<String, Object> request(String mode) {
    var v = new HashMap<String, Object>();
    v.put("requestKey", UUID.randomUUID());
    v.put("title", "공개 조건 시험 대회");
    v.put("description", "실제 서비스와 분리한 검증 데이터");
    v.put("mode", mode);
    v.put("eventId", mode.equals("DISASTER") ? disasters.catalog().events().getFirst().id() : null);
    v.put("districtIds", List.of("11680"));
    v.put("allowedTypes", List.of("RAIN_GARDEN"));
    v.put("opensAt", Instant.now().truncatedTo(ChronoUnit.MINUTES));
    v.put("closesAt", Instant.now().plusSeconds(3600).truncatedTo(ChronoUnit.MINUTES));
    v.put("awards", List.of(Map.of("title", "우수상", "rankFrom", 1, "rankTo", 2, "prizeKrw", 10000)));
    v.put("awardNotice", "공동 순위는 동등 시상하며 종료 후 지급");
    return v;
  }

  JsonNode create(Actor host, String mode) throws Exception {
    return ok(host, "POST", "/competitions", request(mode), 200);
  }

  String base(JsonNode c) {
    return "/competitions/" + c.path("id").asString();
  }

  void join(Actor a, JsonNode c) throws Exception {
    ok(a, "POST", base(c) + "/join", Map.of("rulesHash", c.path("rulesHash").asString()), 200);
  }

  @Test
  void enforcesHostApprovalFrozenRulesIdempotencyAndPrivateResults() throws Exception {
    var owner = host();
    var other = host();
    var player = actor(null);
    var admin = actor(null, true);
    var body = request("REALTIME");
    assertThat(call(player, "POST", "/competitions", body).statusCode()).isEqualTo(403);
    var c = ok(owner, "POST", "/competitions", body, 200);
    assertThat(ok(owner, "POST", "/competitions", body, 200).path("id")).isEqualTo(c.path("id"));
    body.put("title", "다른 조건");
    assertThat(call(owner, "POST", "/competitions", body).statusCode()).isEqualTo(409);
    assertThat(call(other, "GET", base(c) + "/results", null).statusCode()).isEqualTo(404);
    assertThat(call(player, "GET", base(c) + "/results", null).statusCode()).isEqualTo(404);
    assertThat(
            call(player, "POST", base(c) + "/join", Map.of("rulesHash", "0".repeat(64)))
                .statusCode())
        .isEqualTo(409);
    join(player, c);
    join(player, c);
    assertThat(ok(player, "GET", base(c), null, 200).path("participantCount").asInt()).isEqualTo(1);
    ok(admin, "GET", base(c) + "/results", null, 200);
    ok(owner, "GET", base(c) + "/results", null, 200);
    assertThat(call(player, "GET", "/admin/results/seasons", null).statusCode()).isEqualTo(403);
    ok(admin, "GET", "/admin/results/seasons", null, 200);
    var invalid = request("REALTIME");
    invalid.put("districtIds", List.of("INVALID"));
    assertThat(call(owner, "POST", "/competitions", invalid).statusCode()).isEqualTo(400);
    invalid = request("REALTIME");
    invalid.put(
        "awards",
        List.of(
            Map.of("title", "중복", "rankFrom", 1, "rankTo", 2, "prizeKrw", 0),
            Map.of("title", "중복", "rankFrom", 2, "rankTo", 3, "prizeKrw", 0)));
    assertThat(call(owner, "POST", "/competitions", invalid).statusCode()).isEqualTo(400);
    db.update(
        "UPDATE organizations SET approved=false WHERE id=(SELECT organization_id FROM accounts"
            + " WHERE id=?)",
        owner.id());
    assertThat(call(owner, "POST", "/competitions", request("REALTIME")).statusCode())
        .isEqualTo(403);
    assertThat(
            call(
                    actor(null),
                    "POST",
                    base(c) + "/join",
                    Map.of("rulesHash", c.path("rulesHash").asString()))
                .statusCode())
        .isEqualTo(409);
  }

  void schedule(JsonNode c, Instant start, Instant end) {
    var node = (tools.jackson.databind.node.ObjectNode) canonical.tree(c.path("rules").toString());
    node.put("opensAt", start.toString());
    node.put("closesAt", end.toString());
    String rules = canonical.write(node);
    db.update(
        "UPDATE game_competitions SET opens_at=?,closes_at=?,rules=?,rules_hash=? WHERE id=?",
        Timestamp.from(start),
        Timestamp.from(end),
        rules,
        canonical.hash(rules),
        UUID.fromString(c.path("id").asString()));
    db.update(
        "UPDATE game_competition_participants SET joined_at=? WHERE competition_id=?",
        Timestamp.from(start),
        UUID.fromString(c.path("id").asString()));
  }

  UUID install(Actor a, JsonNode c, Instant at, Instant end, String type, String score) {
    var id = UUID.randomUUID();
    var job = UUID.randomUUID();
    db.update(
        "INSERT INTO"
            + " shared_installations(id,district_id,cell_id,owner_id,model_hash,facility_type,area_m2,cost,installed_at,removed_at,season_ends_at,physics_policy)"
            + " VALUES(?,?,?,?,?,?,1,560000,?,?,?,?)",
        id,
        "11680",
        "TEST_" + id,
        a.id(),
        "a".repeat(64),
        type,
        Timestamp.from(at),
        Timestamp.from(end),
        Timestamp.from(end),
        "INSTALLATION_SECOND_V2");
    db.update(
        "INSERT INTO"
            + " shared_physics_jobs(id,installation_id,simulation_start,requested_through,state,lease_token,created_at,finished_at,input_hash,result)"
            + " VALUES(?,?,?,?,'SUCCEEDED',?,?,?,?, '{}')",
        job,
        id,
        Timestamp.from(at),
        Timestamp.from(end),
        UUID.randomUUID(),
        Timestamp.from(at),
        Timestamp.from(end),
        "b".repeat(64));
    if (score != null)
      db.update(
          "INSERT INTO"
              + " game_competition_live_scores(competition_id,installation_id,owner_id,score_m3,evaluated_seconds,evaluated_through,comparison_group_hash,score_policy_sha256,source_job_id)"
              + " VALUES(?,?,?,?,?,?,?,?,?)",
          UUID.fromString(c.path("id").asString()),
          id,
          a.id(),
          new BigDecimal(score),
          (int) Duration.between(at, end).toSeconds(),
          Timestamp.from(end),
          "c".repeat(64),
          policy.sha256(),
          job);
    var week =
        at.atZone(ZoneId.of("Asia/Seoul"))
            .toLocalDate()
            .with(java.time.temporal.TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    if (score != null)
      db.update(
          "INSERT INTO"
              + " shared_weekly_scores(installation_id,week_start,score_m3,evaluated_minutes,evaluated_seconds,evaluated_through,source_job_id,rule_version,score_policy_sha256,comparison_group_hash)"
              + " VALUES(?,?,?,?,?,?,?,'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2',?,?)",
          id,
          java.sql.Date.valueOf(week),
          new BigDecimal(score),
          (int) Math.ceil(Duration.between(at, end).toSeconds() / 60.0),
          (int) Duration.between(at, end).toSeconds(),
          Timestamp.from(end),
          job,
          policy.sha256(),
          "c".repeat(64));
    return id;
  }

  @Test
  void ranksExactTiesExcludesDisallowedFacilitiesAndRetainsInstallationTimes() throws Exception {
    var owner = host();
    var a = actor(null);
    var b = actor(null);
    var c = create(owner, "REALTIME");
    join(a, c);
    join(b, c);
    var end = Instant.now().minusSeconds(600).truncatedTo(ChronoUnit.MINUTES);
    var start = end.minusSeconds(600);
    schedule(c, start, end);
    var installed = start.plusSeconds(17);
    install(a, c, installed, end, "RAIN_GARDEN", "1.123456789");
    install(b, c, installed, end, "RAIN_GARDEN", "1.123456789");
    install(a, c, installed, end, "GREEN_ROOF", "999");
    var results = ok(owner, "GET", base(c) + "/results", null, 200);
    assertThat(results.path("status").asString()).isEqualTo("FINAL");
    var rows = results.path("groups").get(0).path("entries");
    assertThat(rows.size()).isEqualTo(2);
    for (var row : rows) {
      assertThat(row.path("rank").asInt()).isEqualTo(1);
      assertThat(row.path("scoreM3Exact").asString()).isEqualTo("1.123456789");
      assertThat(row.path("installations").size()).isEqualTo(1);
      assertThat(row.path("installations").get(0).path("installedAt").asString())
          .isEqualTo(installed.toString());
    }
    install(a, c, start.plusSeconds(30), end, "RAIN_GARDEN", null);
    assertThat(ok(owner, "GET", base(c) + "/results", null, 200).path("status").asString())
        .isEqualTo("PROVISIONAL");
    var admin = actor(null, true);
    var week =
        start
            .atZone(ZoneId.of("Asia/Seoul"))
            .toLocalDate()
            .with(java.time.temporal.TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    var archive = ok(admin, "GET", "/admin/results/weekly?week=" + week, null, 200);
    assertThat(archive.path("installations").size()).isGreaterThanOrEqualTo(4);
    assertThat(archive.path("period").path("players").size()).isGreaterThanOrEqualTo(2);
    assertThat(call(owner, "POST", base(c) + "/cancel", null).statusCode()).isEqualTo(409);
  }

  UUID historical(Actor a, JsonNode c, String type, String state, Instant created, String score) {
    var id = UUID.randomUUID();
    String frozen = canonical.write(Map.of("scorePolicy", Map.of("sha256", policy.sha256())));
    String placements =
        canonical.write(
            List.of(
                Map.of("districtId", "11680", "facilityType", type, "submissionRulesRaw", frozen)));
    db.update(
        "INSERT INTO"
            + " historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at,source_dataset)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?)",
        id,
        a.id(),
        UUID.randomUUID(),
        "11680",
        "a".repeat(64),
        "b".repeat(64),
        placements,
        state,
        Timestamp.from(created),
        "SEOUL_NGII_GAME_V2");
    db.update(
        "INSERT INTO"
            + " historical_submissions(job_id,event_id,rules_hash,request_raw,cost,difference_m3,score_policy_sha256,comparison_group_hash)"
            + " VALUES(?,?,?,'{}',1000,?,?,?)",
        id,
        c.path("eventId").asString(),
        "d".repeat(64),
        score == null ? null : new BigDecimal(score),
        policy.sha256(),
        "e".repeat(64));
    return id;
  }

  @Test
  void checksHistoricalOwnershipRulesDeadlineAndPostCloseCompletion() throws Exception {
    var owner = host();
    var a = actor(null);
    var b = actor(null);
    var c = create(owner, "DISASTER");
    join(a, c);
    join(b, c);
    var now = Instant.now();
    var valid = historical(a, c, "RAIN_GARDEN", "QUEUED", now, null);
    var foreign = historical(b, c, "RAIN_GARDEN", "SUCCEEDED", now, "9");
    var invalid = historical(a, c, "GREEN_ROOF", "SUCCEEDED", now, "10");
    var before = historical(a, c, "RAIN_GARDEN", "SUCCEEDED", now.minusSeconds(120), "11");
    String path = base(c) + "/submissions";
    String hash = c.path("rulesHash").asString();
    assertThat(call(a, "POST", path, Map.of("jobId", foreign, "rulesHash", hash)).statusCode())
        .isEqualTo(404);
    assertThat(call(a, "POST", path, Map.of("jobId", invalid, "rulesHash", hash)).statusCode())
        .isEqualTo(400);
    assertThat(call(a, "POST", path, Map.of("jobId", before, "rulesHash", hash)).statusCode())
        .isEqualTo(400);
    ok(a, "POST", path, Map.of("jobId", valid, "rulesHash", hash), 200);
    ok(a, "POST", path, Map.of("jobId", valid, "rulesHash", hash), 200);
    var end = now.truncatedTo(ChronoUnit.MINUTES);
    schedule(c, end.minusSeconds(600), end);
    var closed = ok(owner, "GET", base(c), null, 200);
    assertThat(ok(owner, "GET", base(c) + "/results", null, 200).path("status").asString())
        .isEqualTo("PROVISIONAL");
    assertThat(
            call(
                    b,
                    "POST",
                    path,
                    Map.of("jobId", foreign, "rulesHash", closed.path("rulesHash").asString()))
                .statusCode())
        .isEqualTo(409);
    db.update("UPDATE historical_experiments SET state='SUCCEEDED' WHERE id=?", valid);
    db.update(
        "UPDATE historical_submissions SET difference_m3=1.123456789123456789 WHERE job_id=?",
        valid);
    var result = ok(owner, "GET", base(c) + "/results", null, 200);
    assertThat(result.path("status").asString()).isEqualTo("FINAL");
    var entry = result.path("groups").get(0).path("entries").get(0);
    assertThat(entry.path("scoreM3Exact").asString()).isEqualTo("1.123456789123456789");
    assertThat(entry.has("installations")).isFalse();
    var admin = actor(null, true);
    ok(admin, "GET", "/admin/results/historical/" + c.path("eventId").asString(), null, 200);
  }
}
