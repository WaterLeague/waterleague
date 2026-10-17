package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.InstitutionMfaService;
import io.waterleague.common.service.JsonService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.sharedresearch.service.SharedResearchService;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class SharedResearchWorkflowTests {
  static final Path ROOT;

  static {
    try {
      ROOT = Files.createTempDirectory("waterleague-shared-research-").toRealPath();
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  @DynamicPropertySource
  static void properties(DynamicPropertyRegistry r) {
    String url = System.getProperty("waterleague.integration.jdbc");
    if (url == null) throw new IllegalStateException("전용 임시 DB 필요");
    r.add("spring.datasource.url", () -> url);
    r.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    r.add("spring.datasource.username", () -> System.getenv("WL_INTEGRATION_USER"));
    r.add("spring.datasource.password", () -> System.getenv("WL_INTEGRATION_PASSWORD"));
    r.add("waterleague.artifacts", () -> ROOT.toString());
  }

  @AfterAll
  static void cleanup() throws Exception {
    try (var paths = Files.walk(ROOT)) {
      for (var p : paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(p);
    }
  }

  @Value("${local.server.port}")
  int port;

  @Autowired JdbcTemplate db;
  @Autowired JsonService json;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired InstitutionMfaService mfa;
  @Autowired ResearchRepository research;
  @Autowired SharedResearchService service;

  record Actor(UUID id, UUID org, HttpClient client) {}

  record Fixture(UUID id, Path path) {}

  @BeforeEach
  void reset() {
    db.update("DELETE FROM rate_limits");
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM shared_installations");
  }

  Actor actor(boolean institution) throws Exception {
    UUID id = UUID.randomUUID(), org = institution ? UUID.randomUUID() : null;
    if (org != null)
      db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", org, "공동 연구 시험 기관");
    String name = "shared_" + id.toString().substring(0, 8);
    accounts.add(
        new Account(
            id,
            name,
            "공동 시험 회원",
            passwords.encode("test-password-1234"),
            "MEMBER",
            institution ? "INSTITUTION" : "PLAYER",
            "APPROVED",
            org,
            "",
            "",
            true,
            "2419953",
            "AFFILIATED"));
    var actor =
        new Actor(
            id,
            org,
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    var body = new HashMap<String, Object>();
    body.put("username", name);
    body.put("password", "test-password-1234");
    if (org != null) body.put("otp", MfaTests.otp(mfa.provision(id)));
    assertThat(call(actor, "POST", "/auth/login", body).statusCode()).isEqualTo(200);
    return actor;
  }

  HttpResponse<String> call(Actor a, String method, String path, Object body) throws Exception {
    var b = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path));
    if (!method.equals("GET")) {
      var csrf =
          a.client()
              .send(
                  HttpRequest.newBuilder(
                          URI.create("http://127.0.0.1:" + port + "/api/v1/auth/csrf"))
                      .build(),
                  HttpResponse.BodyHandlers.ofString());
      b.header("X-CSRF-TOKEN", json.tree(csrf.body()).path("token").asString())
          .header("Content-Type", "application/json")
          .method(method, HttpRequest.BodyPublishers.ofString(json.write(body)));
    }
    return a.client().send(b.build(), HttpResponse.BodyHandlers.ofString());
  }

  JsonNode get(Actor a, String path) throws Exception {
    var r = call(a, "GET", path, null);
    assertThat(r.statusCode()).as(r.body()).isEqualTo(200);
    return json.tree(r.body());
  }

  void grant(Actor owner, Actor org, boolean value) throws Exception {
    assertThat(
            call(owner, "PUT", "/consents/shared/" + org.org(), Map.of("granted", value))
                .statusCode())
        .isEqualTo(204);
  }

  String manifest(Path dir) throws Exception {
    var hashes = new TreeMap<String, String>();
    try (var files = Files.list(dir)) {
      for (var p : files.toList())
        if (!p.getFileName().toString().equals("manifest.json"))
          hashes.put(p.getFileName().toString(), json.hash(Files.readString(p)));
    }
    String value = json.write(hashes);
    Files.writeString(dir.resolve("manifest.json"), value);
    return json.hash(value);
  }

  Fixture fixture(Actor a) throws Exception {
    UUID i = UUID.randomUUID(), j = UUID.randomUUID(), lease = UUID.randomUUID();
    LocalDate week =
        LocalDate.now(ZoneId.of("Asia/Seoul"))
            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    Instant start = week.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant().plusSeconds(3600),
        end = start.plusSeconds(60);
    var dir = ROOT.resolve("shared-physics").resolve(j.toString()).resolve(lease.toString());
    Files.createDirectories(dir);
    String modelHash = "a".repeat(64);
    var model =
        Map.of(
            "cells",
            List.of(Map.of("id", "G1")),
            "assumptions",
            List.of("SYNTHETIC_TEST_ONLY"),
            "hydrology",
            Map.of(),
            "unitCosts",
            Map.of("RAIN_GARDEN", 560000),
            "budget",
            80000000);
    var forcing =
        Map.of(
            "start",
            start.toString(),
            "end",
            end.toString(),
            "sourceArchive",
            Map.of("complete", true, "missingHashes", List.of()),
            "evaporation",
            Map.of(
                "method",
                "SYNTHETIC_TEST_ONLY",
                "assumptions",
                List.of("SYNTHETIC_TEST_ONLY"),
                "sourceHashes",
                List.of()));
    String modelText = json.write(model), forcingText = json.write(forcing), code = "# 합성 시험 자료\n";
    Files.writeString(dir.resolve("model-source.json"), modelText);
    Files.writeString(dir.resolve("forcing.json"), forcingText);
    Files.writeString(dir.resolve("weekly.py"), code);
    var request =
        Map.of(
            "installationId",
            i,
            "siteModelHash",
            modelHash,
            "modelSha256",
            json.hash(modelText),
            "forcingSha256",
            json.hash(forcingText),
            "weeklyCodeSha256",
            json.hash(code),
            "weeklyRuleVersion",
            "OBSERVED_ACCOUNTED_VOLUME_V1",
            "engine",
            Map.of(),
            "placement",
            Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 10));
    String requestText = json.write(request);
    Files.writeString(dir.resolve("request.json"), requestText);
    var sample = new LinkedHashMap<String, Object>();
    sample.put("at", end.toString());
    for (String name :
        List.of(
            "precipitationM3",
            "infiltrationM3",
            "evaporationM3",
            "surfaceRunoffM3",
            "lidDrainageM3",
            "storageM3",
            "initialStorageM3",
            "accountedDischargeM3",
            "runoffM3s",
            "surfaceDepthMm",
            "soilMoisture",
            "storageDepthMm",
            "balanceResidualM3")) sample.put(name, 0);
    var run = Map.of("samples", List.of(sample), "final", sample);
    Files.writeString(
        dir.resolve("result.json"),
        json.write(
            Map.of(
                "baseline",
                run,
                "strategy",
                run,
                "contribution",
                List.of(Map.of("at", end, "incrementM3", 0, "cumulativeM3", 0)))));
    String anchor = manifest(dir);
    db.update(
        "INSERT INTO"
            + " shared_installations(id,occupied_site,district_id,cell_id,owner_id,model_hash,facility_type,area_m2,cost,installed_at)"
            + " VALUES(?,?,'2419953','G1',?,?,'RAIN_GARDEN',10,5600000,?)",
        i,
        "2419953:G1",
        a.id(),
        modelHash,
        java.sql.Timestamp.from(start));
    String summary =
        json.write(
            Map.of(
                "stationName",
                "합성 시험 전용",
                "simulationStart",
                start,
                "simulatedThrough",
                end,
                "runoffContinuityPercent",
                0,
                "validationLevel",
                "EXPLORATORY"));
    db.update(
        "INSERT INTO"
            + " shared_physics_jobs(id,installation_id,simulation_start,requested_through,state,lease_token,created_at,finished_at,input_hash,result,artifact_manifest_hash)"
            + " VALUES(?,?,?,?,'SUCCEEDED',?,now(),now(),?,?,?)",
        j,
        i,
        java.sql.Timestamp.from(start),
        java.sql.Timestamp.from(end),
        lease,
        json.hash(requestText),
        summary,
        anchor);
    db.update(
        "INSERT INTO"
            + " shared_weekly_scores(installation_id,week_start,score_m3,evaluated_minutes,evaluated_through,source_job_id,rule_version)"
            + " VALUES(?,?,0,1,?,?,'OBSERVED_ACCOUNTED_VOLUME_V1')",
        i,
        java.sql.Date.valueOf(week),
        java.sql.Timestamp.from(end),
        j);
    return new Fixture(j, dir);
  }

  @Test
  void exposesArchivedInitializationAndFacilityEvidenceWithoutReplacingLegacyInputs()
      throws Exception {
    var owner = actor(false);
    var org = actor(true);
    var job = fixture(owner);
    var legacy = get(owner, "/installations/records/" + job.id());
    assertThat(legacy.path("initialization").isNull()).isTrue();
    assertThat(legacy.path("facilityDesign").isNull()).isTrue();
    var result =
        (tools.jackson.databind.node.ObjectNode)
            json.tree(Files.readString(job.path().resolve("result.json")));
    var initialization =
        json.tree(
            json.write(
                Map.of(
                    "method",
                    "SYNTHETIC_ARCHIVED_ONLY",
                    "warmupMinutes",
                    10080,
                    "initialSoilMoisture",
                    0.284,
                    "scoreExcludesWarmup",
                    true)));
    var facility =
        json.tree(
            json.write(
                Map.of(
                    "catalogSha256",
                    "b".repeat(64),
                    "profile",
                    Map.of(
                        "id",
                        "SYNTHETIC_ARCHIVED_PROFILE_ONLY",
                        "parameters",
                        Map.of("soilDepthMm", Map.of("value", 175))))));
    result.set("initialization", initialization);
    result.set("facilityDesign", facility);
    Files.writeString(job.path().resolve("result.json"), json.write(result));
    db.update(
        "UPDATE shared_physics_jobs SET artifact_manifest_hash=? WHERE id=?",
        manifest(job.path()),
        job.id());
    grant(owner, org, true);
    var detail = get(org, "/research/installations/" + job.id());
    assertThat(detail.path("initialization")).isEqualTo(initialization);
    assertThat(detail.path("facilityDesign")).isEqualTo(facility);
    assertThat(detail.path("summary").has("facilityDesign")).isFalse();
    grant(owner, org, false);
    assertThat(call(org, "GET", "/research/installations/" + job.id(), null).statusCode())
        .isEqualTo(404);
    assertThat(get(owner, "/installations/records/" + job.id()).path("facilityDesign"))
        .isEqualTo(facility);
  }

  @Test
  void explicitConsentIsSeparateScopedAndRevocable() throws Exception {
    var owner = actor(false);
    var stranger = actor(false);
    var org = actor(true);
    var other = actor(true);
    var job = fixture(owner);
    assertThat(get(owner, "/consents/shared").toString()).contains("\"granted\":false");
    research.consent(owner.id(), org.org(), true);
    assertThat(get(org, "/research/installations").path("entries")).isEmpty();
    assertThat(call(org, "GET", "/research/installations/" + job.id(), null).statusCode())
        .isEqualTo(404);
    assertThat(call(stranger, "GET", "/installations/records/" + job.id(), null).statusCode())
        .isEqualTo(404);
    assertThat(call(owner, "GET", "/research/installations", null).statusCode()).isEqualTo(403);
    grant(owner, org, true);
    assertThat(get(org, "/research/installations").path("entries")).hasSize(1);
    assertThat(get(other, "/research/installations").path("entries")).isEmpty();
    assertThat(
            call(other, "GET", "/research/installations/" + job.id() + "/bundle", null)
                .statusCode())
        .isEqualTo(404);
    var detail = get(org, "/research/installations/" + job.id());
    assertThat(detail.path("frames")).hasSize(1);
    assertThat(detail.toString()).doesNotContain("passwordHash", "username", "ownerId");
    assertThat(
            call(org, "GET", "/research/installations/" + job.id() + "/bundle", null).statusCode())
        .isEqualTo(200);
    assertThat(get(owner, "/installations/records").path("entries")).hasSize(1);
    grant(owner, org, false);
    assertThat(get(org, "/research/installations").path("entries")).isEmpty();
    assertThat(call(org, "GET", "/research/installations/" + job.id(), null).statusCode())
        .isEqualTo(404);
    assertThat(
            call(org, "GET", "/research/installations/" + job.id() + "/bundle", null).statusCode())
        .isEqualTo(404);
    assertThat(get(owner, "/installations/records/" + job.id()).path("jobId").asString())
        .isEqualTo(job.id().toString());
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE actor_id=? AND"
                    + " action='SHARED_RESEARCH_EXPORT'",
                Integer.class,
                org.id()))
        .isEqualTo(1);
  }

  @Test
  void revocationOfAccountOrOrganizationBlocksExistingRecordAccess() throws Exception {
    var owner = actor(false);
    var org = actor(true);
    var job = fixture(owner);
    grant(owner, org, true);
    db.update("UPDATE accounts SET enabled=false WHERE id=?", owner.id());
    assertThat(get(org, "/research/installations").path("entries")).isEmpty();
    assertThat(call(org, "GET", "/research/installations/" + job.id(), null).statusCode())
        .isEqualTo(404);
    db.update("UPDATE accounts SET enabled=true WHERE id=?", owner.id());
    db.update("UPDATE organizations SET approved=false WHERE id=?", org.org());
    assertThat(
            call(org, "GET", "/research/installations/" + job.id() + "/bundle", null).statusCode())
        .isEqualTo(403);
  }

  @Test
  void exportsWeeklyObservationFileCountAndRejectsMislabeledRawSource() throws Exception {
    var owner = actor(false);
    var job = fixture(owner);
    var directory = job.path();
    for (int minute = 0; minute < 11000; minute++) {
      String raw = "SYNTHETIC_ARCHIVE_SIZE_TEST_ONLY " + minute;
      String sha = json.hash(raw);
      Files.writeString(directory.resolve(sha + ".txt"), raw);
      Files.writeString(directory.resolve(sha + ".json"), "{}");
    }
    db.update(
        "UPDATE shared_physics_jobs SET artifact_manifest_hash=? WHERE id=?",
        manifest(directory),
        job.id());
    var response =
        owner
            .client()
            .send(
                HttpRequest.newBuilder(
                        URI.create(
                            "http://127.0.0.1:"
                                + port
                                + "/api/v1/installations/records/"
                                + job.id()
                                + "/bundle"))
                    .build(),
                HttpResponse.BodyHandlers.ofByteArray());
    assertThat(response.statusCode()).isEqualTo(200);
    int entries = 0;
    try (var zip =
        new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(response.body()))) {
      while (zip.getNextEntry() != null) {
        entries++;
        zip.closeEntry();
      }
    }
    assertThat(entries).isEqualTo(22007);
    Files.writeString(directory.resolve("b".repeat(64) + ".txt"), "SYNTHETIC_WRONG_HASH_TEST_ONLY");
    db.update(
        "UPDATE shared_physics_jobs SET artifact_manifest_hash=? WHERE id=?",
        manifest(directory),
        job.id());
    assertThat(
            call(owner, "GET", "/installations/records/" + job.id() + "/bundle", null).statusCode())
        .isEqualTo(503);
  }

  @Test
  void anchoredManifestRejectsChangedFilesEvenWithRewrittenHashesAndSymlinks() throws Exception {
    var owner = actor(false);
    var job = fixture(owner);
    var dir = job.path();
    String original = Files.readString(dir.resolve("result.json")),
        anchor = Files.readString(dir.resolve("manifest.json"));
    Files.writeString(dir.resolve("result.json"), "{}");
    manifest(dir);
    assertThat(
            call(owner, "GET", "/installations/records/" + job.id() + "/bundle", null).statusCode())
        .isEqualTo(503);
    Files.writeString(dir.resolve("result.json"), original);
    Files.writeString(dir.resolve("manifest.json"), anchor);
    var outside = ROOT.resolve("outside-" + UUID.randomUUID() + ".json");
    Files.move(dir.resolve("result.json"), outside);
    Files.createSymbolicLink(dir.resolve("result.json"), outside);
    assertThat(call(owner, "GET", "/installations/records/" + job.id(), null).statusCode())
        .isEqualTo(503);
    Files.delete(dir.resolve("result.json"));
    Files.move(outside, dir.resolve("result.json"));
    assertThat(get(owner, "/installations/records/" + job.id()).path("sampleCount").asInt())
        .isEqualTo(1);
    db.update("UPDATE shared_physics_jobs SET artifact_manifest_hash=NULL WHERE id=?", job.id());
    assertThat(
            call(owner, "GET", "/installations/records/" + job.id() + "/bundle", null).statusCode())
        .isEqualTo(409);
  }
}
