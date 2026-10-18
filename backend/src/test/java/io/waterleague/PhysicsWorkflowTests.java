package io.waterleague;

import static java.sql.Timestamp.from;
import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.net.*;
import java.net.http.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class PhysicsWorkflowTests {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Value("${local.server.port}")
  int port;

  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired InstallationService installations;
  UUID installation;
  String username;
  final HttpClient client = HttpClient.newHttpClient();

  @BeforeEach
  void prepare() {
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM budget_ledger_entries");
    db.update("DELETE FROM shared_installations");
    UUID id = UUID.randomUUID();
    username = "physics_" + id.toString().substring(0, 8);
    accounts.add(
        new Account(
            id,
            username,
            "물리 시험",
            "NOT_A_LOGIN",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            "2410520",
            "AFFILIATED"));
    installation =
        installations
            .install(
                username,
                new InstallRequest("2410520", "G1", FacilityType.RAIN_GARDEN, BigDecimal.TEN))
            .id();
  }

  HttpResponse<String> get(String path) throws Exception {
    return client.send(
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).GET().build(),
        HttpResponse.BodyHandlers.ofString());
  }

  HttpResponse<String> physics() throws Exception {
    return get("/api/v1/installations/" + installation + "/physics");
  }

  UUID job(String state, Instant created, Instant through, String result, String error) {
    UUID id = UUID.randomUUID();
    db.update(
        "INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,"
            + "state,lease_token,lease_until,created_at,finished_at,input_hash,result,error_code)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        id,
        installation,
        from(through.minusSeconds(600)),
        from(through),
        state,
        UUID.randomUUID(),
        state.equals("RUNNING") ? from(created.plusSeconds(240)) : null,
        from(created),
        state.equals("RUNNING") ? null : from(created.plusSeconds(1)),
        result == null ? null : "a".repeat(64),
        result,
        error);
    return id;
  }

  @Test
  void exposesPublicStatusWithoutPrivateArtifactsOrInventedZeros() throws Exception {
    var response = physics();
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
    assertThat(response.body())
        .contains("\"status\":\"WAITING\"", "\"result\":null")
        .doesNotContain("lease", "inputHash", "password");
    assertThat(get("/api/v1/installations/sites/2410520/G1").statusCode()).isEqualTo(200);
    var id = job("RUNNING", Instant.now(), Instant.now().minusSeconds(120), null, null);
    assertThat(physics().body()).contains("\"status\":\"RUNNING\"");
    db.update(
        "UPDATE shared_physics_jobs SET created_at=? WHERE id=?",
        from(Instant.now().minusSeconds(300)),
        id);
    assertThat(physics().body()).contains("\"status\":\"RUNNING\"");
    db.update(
        "UPDATE shared_physics_jobs SET lease_until=? WHERE id=?",
        from(Instant.now().minusSeconds(1)),
        id);
    assertThat(physics().body()).contains("\"status\":\"UNAVAILABLE\"");
    assertThat(get("/api/v1/facilities/epa-designs-v1").body())
        .contains("EPA_LID_PUBLIC_DESIGNS_V1", "EPA_GR_150_V1");
    assertThat(get("/api/v1/installations/sites/2410520/G1").body())
        .contains("OBSERVED_7_DAY_CONTINUOUS_SPINUP_V1", "RG_NATIVE_SOIL_SEEPAGE_V1",
            "UNLINED_DESIGN_NOT_SITE_CONFIRMED", "\"storageThicknessMm\":0");
    installations.remove(username, installation);
    assertThat(physics().statusCode()).isEqualTo(404);
  }

  @Test
  void preservesLastValidResultWithTimestampWhenNewObservationsFail() throws Exception {
    var through = Instant.now().minusSeconds(600);
    String result =
        """
        {"stationId":"421","stationName":"시험 관측소","simulationStart":"2026-10-12T00:00:00Z",
         "simulatedThrough":"%s","engineVersion":"5.2.4","validationLevel":"EXPLORATORY",
         "precipitationM3":1,"infiltrationM3":0.2,"evaporationM3":0,"runoffM3":0.3,
         "storageM3":0.5,"surfaceDepthMm":0,"soilMoisture":0.2,"storageDepthMm":0,
         "runoffContinuityPercent":0.001,"evaporationMethod":"ASSUMED_MODEL_CONSTANT",
         "initialState":"OBSERVED_7_DAY_CONTINUOUS_SPINUP_V1",
         "initialization":{"warmupMinutes":10080,"scoreExcludesWarmup":true},
         "facilityDesign":{"profile":{"id":"EPA_RG_610_V1"}}}
        """
            .formatted(through);
    job("SUCCEEDED", Instant.now().minusSeconds(590), through, result, null);
    assertThat(physics().body()).contains("\"status\":\"DELAYED\"");
    job("FAILED", Instant.now(), through.plusSeconds(120), null, "KMA_UNAVAILABLE");
    assertThat(physics().body())
        .contains(
            "\"status\":\"UNAVAILABLE\"",
            "기상청 응답",
            "\"infiltrationM3\":0.2",
            through.toString(),
            "\"warmupMinutes\":10080",
            "EPA_RG_610_V1");
  }
}
