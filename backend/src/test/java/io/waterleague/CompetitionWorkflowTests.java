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
    String secret = admin ? mfa.provision(id) : null;
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
  void managerAnalyticsUsesAllRecordsAndRejectsParticipantsAndOtherOrganizations()
      throws Exception {
    var owner = host();
    var other = host();
    var player = actor(null);
    var admin = actor(null, true);
    var c = create(owner, "REALTIME");
    join(player, c);
    Instant at = competitionRepo.joined(UUID.fromString(c.path("id").asString()), player.id());
    var competitionId = UUID.fromString(c.path("id").asString());
    var passwordHash = accounts.byId(player.id()).orElseThrow().passwordHash();
    for (int i = 0; i < 103; i++) {
      var selected = player;
      if (i > 0) {
        var id = UUID.randomUUID();
        accounts.add(
            new Account(
                id,
                "qa_analysis_" + i,
                "분석검증" + i,
                passwordHash,
                "MEMBER",
                "PLAYER",
                "APPROVED",
                null,
                "",
                "",
                true,
                "11680",
                "AFFILIATED"));
        competitionRepo.join(competitionId, id, c.path("rulesHash").asString());
        selected = new Actor(id, player.client());
      }
      Instant joined = competitionRepo.joined(competitionId, selected.id());
      install(selected, c, joined, joined.plusSeconds(60), "RAIN_GARDEN", null);
    }
    var path = base(c) + "/analytics";
    var data = ok(owner, "GET", path, null, 200);
    assertThat(data.path("facts").path("records").longValue()).isEqualTo(103);
    assertThat(data.path("facts").path("participants").longValue()).isEqualTo(103);
    assertThat(data.path("facts").path("facilities").get(0).path("count").longValue())
        .isEqualTo(103);
    assertThat(data.path("facts").path("scoredRecords").longValue()).isZero();
    assertThat(data.path("facts").path("scoreGroups").size()).isZero();
    assertThat(call(owner, "GET", path, null).headers().firstValue("Cache-Control"))
        .hasValue("no-store");
    assertThat(data.toString()).doesNotContain(player.id().toString(), "nickname", "playerId");
    ok(admin, "GET", path, null, 200);
    assertThat(call(player, "GET", path, null).statusCode()).isEqualTo(404);
    assertThat(call(other, "GET", path, null).statusCode()).isEqualTo(404);
    assertThat(
            call(
                    player,
                    "POST",
                    path + "/summary",
                    Map.of("snapshotHash", data.path("snapshotHash").asString()))
                .statusCode())
        .isEqualTo(404);
    assertThat(
            call(player, "GET", "/admin/results/weekly/analytics?week=2026-10-19", null)
                .statusCode())
        .isEqualTo(403);
    var week =
        at.atZone(ZoneId.of("Asia/Seoul"))
            .toLocalDate()
            .with(java.time.temporal.TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    assertThat(
            ok(admin, "GET", "/admin/results/weekly/analytics?week=" + week, null, 200)
                .path("facts")
                .path("records")
                .longValue())
        .isZero();
    var event = disasters.catalog().events().getFirst().id();
    assertThat(
            ok(admin, "GET", "/admin/results/historical/" + event + "/analytics", null, 200)
                .path("facts")
                .path("records")
                .longValue())
        .isZero();
  }

  @Test
  void immediateRealtimeInstallationUsesSameSecondAsParticipation() throws Exception {
    var player = actor(null);
    var c = create(host(), "REALTIME");
    join(player, c);
    var id = UUID.fromString(c.path("id").asString());
    var joined = competitionRepo.joined(id, player.id());
    assertThat(joined).isEqualTo(joined.truncatedTo(ChronoUnit.SECONDS));
    var installation =
        install(
            player, c, joined, Instant.parse(c.path("closesAt").asString()), "RAIN_GARDEN", "1");
    var entries =
        ok(player, "GET", base(c) + "/results", null, 200).path("groups").get(0).path("entries");
    assertThat(entries.size()).isEqualTo(1);
    assertThat(entries.get(0).path("installations").get(0).path("id").asString())
        .isEqualTo(installation.toString());
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
            + " shared_installations(id,district_id,cell_id,owner_id,model_hash,facility_type,area_m2,cost,installed_at,removed_at,season_ends_at,physics_policy,competition_id)"
            + " VALUES(?,?,?,?,?,?,1,560000,?,?,?,?,?)",
        id,
        "11680",
        "TEST_" + id,
        a.id(),
        "a".repeat(64),
        type,
        Timestamp.from(at),
        Timestamp.from(end),
        Timestamp.from(end),
        "INSTALLATION_SECOND_V2",
        UUID.fromString(c.path("id").asString()));
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
    var own = ok(a, "GET", base(c) + "/results?page=1", null, 200).path("groups").get(0);
    assertThat(own.path("entries").size()).isZero();
    assertThat(own.path("ownEntries").get(0).path("rank").asInt()).isEqualTo(1);
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
    assertThat(archive.path("installations").size()).isZero();
    assertThat(archive.path("period").path("players").size()).isZero();
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
            + " historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at,source_dataset,competition_id)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        id,
        a.id(),
        UUID.randomUUID(),
        "11680",
        "a".repeat(64),
        "b".repeat(64),
        placements,
        state,
        Timestamp.from(created),
        "SEOUL_NGII_GAME_V2",
        UUID.fromString(c.path("id").asString()));
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

  @Autowired io.waterleague.installation.repository.SiteCatalogRepository sites;
  @Autowired io.waterleague.historical.service.HistoricalDesignService designService;
  @Autowired io.waterleague.budget.service.BudgetService budgets;

  @Test
  void realtimeCompetitionAllowsOtherDistrictsButWeeklyAndMapLimitsRemain() throws Exception {
    var organizer = host();
    var player = actor(null);
    db.update("UPDATE accounts SET district_id='11110' WHERE id=?", player.id());
    var competition = create(organizer, "REALTIME");
    join(player, competition);
    var site =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(
                v ->
                    v.existingInfrastructure() == null
                        && v.allowedTypes().contains("RAIN_GARDEN")
                        && v.maxAreaM2().compareTo(BigDecimal.ONE) >= 0)
            .findFirst()
            .orElseThrow();
    var placement =
        Map.of(
            "districtId",
            "11680",
            "cellId",
            site.cellId(),
            "facilityType",
            "RAIN_GARDEN",
            "areaM2",
            1);
    var path = "/installations?competitionId=" + competition.path("id").asString();
    var installed = ok(player, "POST", path, placement, 201);
    assertThat(installed.path("districtId").asString()).isEqualTo("11680");
    assertThat(call(player, "POST", "/installations", placement).statusCode()).isEqualTo(403);
    var outside = new HashMap<String, Object>(placement);
    outside.put("districtId", "11110");
    assertThat(call(player, "POST", path, outside).statusCode()).isEqualTo(422);
    var unaffiliated = actor(null);
    db.update(
        "UPDATE accounts SET district_id=NULL,affiliation_type=NULL WHERE id=?", unaffiliated.id());
    join(unaffiliated, competition);
    ok(unaffiliated, "POST", path, placement, 201);
    assertThat(call(unaffiliated, "POST", "/installations", placement).statusCode()).isEqualTo(409);
    assertThat(
            db.queryForObject(
                "SELECT district_id FROM accounts WHERE id=?", String.class, player.id()))
        .isEqualTo("11110");
  }

  @Test
  void validatesFrozenBudgetAndSerializesSpendingWithoutTouchingGeneralBudget() throws Exception {
    var h = host();
    var player = actor(null);
    var stranger = actor(null);
    var siteRows =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(
                v ->
                    v.existingInfrastructure() == null
                        && v.allowedTypes().contains("RAIN_GARDEN")
                        && v.maxAreaM2().compareTo(BigDecimal.ONE) >= 0)
            .limit(2)
            .toList();
    assertThat(siteRows).hasSize(2);
    long cap =
        siteRows
            .getFirst()
            .unitCosts()
            .get("RAIN_GARDEN")
            .multiply(new BigDecimal("1.5"))
            .setScale(0, java.math.RoundingMode.CEILING)
            .longValueExact();
    var body = request("REALTIME");
    body.put("budgetMode", "CUSTOM");
    body.put("personalBudgetKrw", cap);
    var c = ok(h, "POST", "/competitions", body, 200);
    join(player, c);
    var id = c.path("id").asString();
    assertThat(c.path("rules").path("personalBudgetKrw").asLong()).isEqualTo(cap);
    body.put("personalBudgetKrw", cap + 1);
    assertThat(call(h, "POST", "/competitions", body).statusCode()).isEqualTo(409);
    var bad = request("REALTIME");
    bad.put("budgetMode", "CUSTOM");
    assertThat(call(h, "POST", "/competitions", bad).statusCode()).isEqualTo(400);
    bad.put("personalBudgetKrw", 0);
    assertThat(call(h, "POST", "/competitions", bad).statusCode()).isEqualTo(400);
    bad.put("personalBudgetKrw", 1.5);
    assertThat(call(h, "POST", "/competitions", bad).statusCode()).isEqualTo(400);
    var large = request("REALTIME");
    large.put("budgetMode", "CUSTOM");
    large.put("personalBudgetKrw", 3000000000L);
    var larger = ok(h, "POST", "/competitions", large, 200);
    join(player, larger);
    assertThat(
            ok(player, "GET", "/budget?competitionId=" + larger.path("id").asString(), null, 200)
                .path("remainingKrw")
                .asLong())
        .isEqualTo(3000000000L);
    assertThat(call(stranger, "GET", "/budget?competitionId=" + id, null).statusCode())
        .isEqualTo(403);
    assertThat(call(stranger, "GET", "/installations?competitionId=" + id, null).statusCode())
        .isEqualTo(403);
    var first = siteRows.getFirst();
    var install =
        Map.of(
            "districtId",
            "11680",
            "cellId",
            first.cellId(),
            "facilityType",
            "RAIN_GARDEN",
            "areaM2",
            1);
    ok(player, "POST", "/installations", install, 201);
    assertThat(call(stranger, "POST", "/installations?competitionId=" + id, install).statusCode())
        .isEqualTo(403);
    var before = ok(player, "GET", "/budget", null, 200).path("remainingKrw");
    var futures =
        siteRows.stream()
            .map(
                site ->
                    java.util.concurrent.CompletableFuture.supplyAsync(
                        () -> {
                          try {
                            return call(
                                    player,
                                    "POST",
                                    "/installations?competitionId=" + id,
                                    Map.of(
                                        "districtId",
                                        "11680",
                                        "cellId",
                                        site.cellId(),
                                        "facilityType",
                                        "RAIN_GARDEN",
                                        "areaM2",
                                        1))
                                .statusCode();
                          } catch (Exception e) {
                            throw new RuntimeException(e);
                          }
                        }))
            .toList();
    var statuses = futures.stream().map(java.util.concurrent.CompletableFuture::join).toList();
    assertThat(statuses.stream().filter(code -> code == 201).count()).isEqualTo(1);
    assertThat(statuses.stream().filter(code -> code >= 400).count()).isEqualTo(1);
    assertThat(ok(player, "GET", "/budget", null, 200).path("remainingKrw")).isEqualTo(before);
    assertThat(ok(player, "GET", "/installations?competitionId=" + id, null, 200).size())
        .isEqualTo(1);
    assertThat(ok(player, "GET", "/installations", null, 200).size()).isEqualTo(1);
    var close = Instant.parse(c.path("closesAt").asString());
    assertThat(
            db.queryForObject(
                    "SELECT season_ends_at FROM shared_installations WHERE competition_id=?",
                    Timestamp.class,
                    UUID.fromString(id))
                .toInstant())
        .isEqualTo(close);
  }

  @Test
  void isolatesDisasterDesignsJobsAndSubmissionBudgetsAcrossCompetitions() throws Exception {
    var h = host();
    var p = actor(null);
    var event = disasters.catalog().events().getFirst();
    var site =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(
                v ->
                    v.existingInfrastructure() == null
                        && v.allowedTypes().contains("RAIN_GARDEN")
                        && v.maxAreaM2().compareTo(BigDecimal.TEN) >= 0)
            .findFirst()
            .orElseThrow();
    var body = request("DISASTER");
    body.put("budgetMode", "CUSTOM");
    body.put("personalBudgetKrw", 1000000000L);
    var c = ok(h, "POST", "/competitions", body, 200);
    join(p, c);
    String scope = "?competitionId=" + c.path("id").asString();
    String path = "/historical/designs/" + event.id();
    var item =
        Map.of(
            "id",
            UUID.randomUUID(),
            "districtId",
            "11680",
            "cellId",
            site.cellId(),
            "facilityType",
            "RAIN_GARDEN",
            "areaM2",
            10,
            "installedAt",
            Instant.parse(event.regions().getFirst().start()).plusSeconds(60));
    var designRequest =
        Map.of(
            "requestKey",
            UUID.randomUUID(),
            "baseRevision",
            0,
            "elapsedSeconds",
            120,
            "placements",
            List.of(item));
    var saved = ok(p, "PUT", path + scope, designRequest, 200);
    assertThat(saved.path("snapshot").path("budgetPolicy").path("personalLimitKrw").asLong())
        .isEqualTo(1000000000L);
    assertThat(ok(p, "GET", path, null, 200).path("revision").asInt()).isZero();
    ok(
        p,
        "PUT",
        path,
        Map.of(
            "requestKey",
            UUID.randomUUID(),
            "baseRevision",
            0,
            "elapsedSeconds",
            120,
            "placements",
            List.of(item)),
        200);
    assertThat(ok(p, "GET", path + scope, null, 200).path("snapshotSha256"))
        .isEqualTo(saved.path("snapshotSha256"));
    String model =
        event.regions().stream()
            .filter(v -> v.districtId().equals("11680"))
            .findFirst()
            .orElseThrow()
            .modelHash();
    var run =
        Map.of(
            "requestKey",
            UUID.randomUUID(),
            "districtId",
            "11680",
            "modelHash",
            model,
            "eventId",
            event.id(),
            "designRevision",
            1,
            "temporalPolicy",
            "INSTALLATION_TIME_EXPERIMENT_V1",
            "placements",
            List.of(
                Map.of(
                    "cellId",
                    site.cellId(),
                    "facilityType",
                    "RAIN_GARDEN",
                    "areaM2",
                    10,
                    "installedAt",
                    item.get("installedAt"),
                    "siteModelHash",
                    site.modelHash())));
    var play = ok(p, "POST", "/historical" + scope, run, 202);
    assertThat(
            play.path("placements").get(0).path("budgetPolicy").path("personalLimitKrw").asLong())
        .isEqualTo(1000000000L);
    assertThat(call(p, "POST", "/historical", run).statusCode()).isEqualTo(409);
    var submitted =
        ok(
            p,
            "POST",
            path + "/submissions" + scope,
            Map.of(
                "requestKey",
                UUID.randomUUID(),
                "revision",
                1,
                "snapshotSha256",
                saved.path("snapshotSha256").asString()),
            202);
    assertThat(ok(p, "GET", "/historical/submissions?eventId=" + event.id(), null, 200).size())
        .isZero();
    assertThat(
            ok(
                    p,
                    "GET",
                    "/historical/submissions?eventId="
                        + event.id()
                        + "&competitionId="
                        + c.path("id").asString(),
                    null,
                    200)
                .size())
        .isEqualTo(1);
    ok(
        p,
        "POST",
        base(c) + "/submissions",
        Map.of(
            "jobId", submitted.path("id").asString(), "rulesHash", c.path("rulesHash").asString()),
        200);
    var otherBody = request("DISASTER");
    otherBody.put("budgetMode", "CUSTOM");
    otherBody.put("personalBudgetKrw", 2000000000L);
    var other = ok(h, "POST", "/competitions", otherBody, 200);
    join(p, other);
    assertThat(
            call(
                    p,
                    "POST",
                    base(other) + "/submissions",
                    Map.of(
                        "jobId",
                        submitted.path("id").asString(),
                        "rulesHash",
                        other.path("rulesHash").asString()))
                .statusCode())
        .isEqualTo(400);
  }
}
