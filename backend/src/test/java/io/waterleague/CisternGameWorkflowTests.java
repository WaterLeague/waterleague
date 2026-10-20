package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.historical.dto.*;
import io.waterleague.historical.service.*;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.physics.service.PhysicsService;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.nio.file.*;
import java.net.URI;
import java.net.http.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class CisternGameWorkflowTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(org.springframework.test.context.DynamicPropertyRegistry r) {
    SharedInstallationTests.integrationDatabase(r);
  }

  @Autowired SiteCatalogRepository sites;
  @Autowired InstallationService installations;
  @Autowired AccountRepository accounts;
  @Autowired BudgetService budgets;
  @Autowired HistoricalDesignService designs;
  @Autowired HistoricalSubmissionService submissions;
  @Autowired HistoricalService history;
  @Autowired DisasterService disasters;
  @Autowired PhysicsService physics;
  @Autowired JdbcTemplate db;
  @Autowired JsonService json;
  @org.springframework.beans.factory.annotation.Value("${local.server.port}") int port;

  @Test
  @DisabledIfSystemProperty(named = "waterleague.integration.cistern.readback", matches = "true")
  void installsOnBuildingChargesBudgetAndSubmitsSavedGameDesign() throws Exception {
    UUID owner = UUID.randomUUID();
    String username = "cistern_" + owner.toString().substring(0, 8);
    accounts.add(new Account(owner, username, "이용조 시험", "NOT_A_LOGIN", "MEMBER", "PLAYER",
        "APPROVED", null, "", "", true, "11200", "AFFILIATED"));
    var site = NativeSiteFixtures.sites(sites, "11200").values().stream()
        .filter(s -> s.kind().equals("ROOF") && s.existingInfrastructure() == null
            && s.maxAreaM2().compareTo(new BigDecimal("235")) >= 0).findFirst().orElseThrow();
    assertThat(site.allowedTypes()).contains("RAINWATER_CISTERN");
    var ground = NativeSiteFixtures.cell(sites, "11200", FacilityType.RAIN_GARDEN, 0);
    assertThatThrownBy(() -> installations.install(username, new InstallRequest(
        "11200", ground.cellId(), FacilityType.RAINWATER_CISTERN, BigDecimal.TEN)))
        .isInstanceOf(DomainException.class);
    var request = new InstallRequest("11200", site.cellId(), FacilityType.RAINWATER_CISTERN,
        new BigDecimal("235"));
    var installed = installations.install(username, request);
    assertThat(installed.cost()).isEqualByComparingTo("2857130");
    assertThat(budgets.view(owner).allocatedKrw()).isEqualByComparingTo(installed.cost());
    assertThatThrownBy(() -> installations.install(username, request))
        .isInstanceOf(DomainException.class);
    assertThat(db.queryForObject("SELECT count(*) FROM budget_ledger_entries WHERE installation_id=?",
        Integer.class, installed.id())).isEqualTo(1);

    var event = disasters.catalog().events().stream()
        .filter(e -> e.id().equals("seoul-20220808")).findFirst().orElseThrow();
    var region = event.regions().stream().filter(r -> r.districtId().equals("11200"))
        .findFirst().orElseThrow();
    var design = designs.save(owner, event.id(), new HistoricalDesignRequest(UUID.randomUUID(),
        0, 137, List.of(new HistoricalDesignRequest.Item(UUID.randomUUID(), "11200",
        site.cellId(), FacilityType.RAINWATER_CISTERN, new BigDecimal("235"),
        Instant.parse(region.start()).plusSeconds(137)))));
    var experiment = history.create(owner, new HistoricalRequest(UUID.randomUUID(), "11200",
        region.modelHash(), List.of(new HistoricalRequest.Item(site.cellId(),
            FacilityType.RAINWATER_CISTERN, new BigDecimal("235"),
            Instant.parse(region.start()).plusSeconds(137), site.modelHash())),
        site.cellId(), "INSTALLATION_TIME_EXPERIMENT_V1", null, design.revision(), event.id()));
    assertThat(experiment.placements().get(0).path("initializationSensitivity").asString())
        .isEqualTo("SELECTED_CISTERN_7_DAY_STORAGE_V3");
    var reference = new HistoricalDesignSubmissionRequest(UUID.randomUUID(),
        design.revision(), design.snapshotSha256());
    var submitted = submissions.submitSaved(owner, event.id(), reference);
    assertThat(submissions.submitSaved(owner, event.id(), reference).id()).isEqualTo(submitted.id());
    assertThat(designs.get(owner, event.id()).snapshotSha256()).isEqualTo(design.snapshotSha256());
    var export = System.getProperty("waterleague.integration.cistern.fixture");
    if (export != null) Files.writeString(Path.of(export), json.write(Map.of(
        "ownerId", owner, "installationId", installed.id(), "submissionId", submitted.id(),
        "experimentId", experiment.id(),
        "eventId", event.id(), "forcingHash", region.modelHash(), "site", site,
        "costKrw", installed.cost(), "design", design)), StandardOpenOption.CREATE_NEW);
  }

  @Test
  @EnabledIfSystemProperty(named = "waterleague.integration.cistern.readback", matches = "true")
  void readsWorkerStorageAndPublishedSubmissionWithoutLosingCisternFields() throws Exception {
    var data = json.tree(Files.readString(Path.of(
        System.getProperty("waterleague.integration.cistern.fixture"))));
    var id = UUID.fromString(data.path("installationId").asString());
    var actual = physics.latest(id);
    assertThat(actual.result()).isNotNull();
    assertThat(actual.result().cistern().path("capacityM3").asDouble()).isEqualTo(2.35);
    assertThat(actual.result().cistern().path("reuseM3").isNull()).isTrue();
    var demand = actual.result().cistern().path("demandScenario");
    assertThat(demand.path("status").asString()).isEqualTo("SUCCEEDED");
    assertThat(demand.path("evaluationSeconds").asDouble()).isEqualTo(3600);
    assertThat(demand.path("rankingEligible").asBoolean()).isFalse();
    assertThat(demand.path("observedReuseM3").isNull()).isTrue();
    var response = HttpClient.newHttpClient().send(HttpRequest.newBuilder(
        URI.create("http://127.0.0.1:" + port + "/api/v1/installations/" + id + "/physics"))
        .GET().build(), HttpResponse.BodyHandlers.ofString());
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(json.tree(response.body()).path("result").path("cistern").path("demandScenario"))
        .isEqualTo(demand);
    Files.writeString(Path.of(System.getProperty("waterleague.integration.cistern.fixture")
        + ".http.json"), response.body(), StandardOpenOption.CREATE_NEW);
    var experiment = history.view(history.require(UUID.fromString(data.path("ownerId").asString()),
        UUID.fromString(data.path("experimentId").asString())));
    var experimentDemand = experiment.result().path("facilities").get(0).path("cistern").path("demandScenario");
    assertThat(experiment.state()).isEqualTo("SUCCEEDED");
    assertThat(experimentDemand.path("evaluationSeconds").asDouble()).isEqualTo(21403);
    assertThat(experimentDemand.path("observedReuseM3").isNull()).isTrue();
    var sensitivity = experiment.result().path("initializationSensitivity");
    assertThat(sensitivity.path("schemaVersion").asInt()).isEqualTo(3);
    assertThat(sensitivity.path("status").asString()).isEqualTo("SUCCEEDED");
    assertThat(sensitivity.path("cases").size()).isEqualTo(4);
    for (var condition : sensitivity.path("cases")) {
      assertThat(condition.path("status").asString()).isEqualTo("SUCCEEDED");
      assertThat(condition.path("nativeSeedStorageM3").asDouble())
          .isEqualTo(condition.path("seedSaturationPercent").asInt() == 0 ? 0 : 2.35);
    }
    var comparison = actual.result().runoffComparison();
    assertThat(comparison.path("schemaVersion").asInt()).isEqualTo(3);
    assertThat(comparison.path("detention").path("status").asString()).isEqualTo("COMPARABLE");
    assertThat(comparison.path("detention").path("rankingEligible").asBoolean()).isFalse();
    assertThat(comparison.path("cases").get(0).path("metrics").path("timing")
        .path("centroidSeconds").isNumber()).isTrue();
    var record = submissions.get(UUID.fromString(data.path("ownerId").asString()),
        UUID.fromString(data.path("submissionId").asString()));
    assertThat(record.state()).isEqualTo("SUCCEEDED");
    assertThat(record.result().path("rankingStatus").asString()).isEqualTo("COMPARABLE");
    var stored = json.tree(db.queryForObject(
        "SELECT result::text FROM historical_experiments WHERE id=?", String.class, record.id()));
    var submittedComparison = stored.path("districts").get(0).path("result")
        .path("facilities").get(0).path("runoffComparison");
    var submittedDemand = stored.path("districts").get(0).path("result")
        .path("facilities").get(0).path("cistern").path("demandScenario");
    assertThat(submittedDemand.path("status").asString()).isEqualTo("SUCCEEDED");
    assertThat(submittedDemand.path("suppliedM3").asDouble()).isGreaterThan(0);
    assertThat(submittedDemand.path("rankingEligible").asBoolean()).isFalse();
    assertThat(submittedComparison.path("schemaVersion").asInt()).isEqualTo(3);
    assertThat(submittedComparison.path("detention").path("centroidDelaySeconds").isNumber()).isTrue();
    assertThat(json.write(submissions.board(data.path("eventId").asString())))
        .contains(data.path("submissionId").asString());
  }
}
