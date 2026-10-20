package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.service.JsonService;
import io.waterleague.cost.repository.GamePriceCatalog;
import io.waterleague.cost.service.CostService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.historical.dto.*;
import io.waterleague.historical.service.*;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

@SpringBootTest
@ActiveProfiles("local")
class PriceVersionWorkflowTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry r) {
    SharedInstallationTests.integrationDatabase(r);
  }

  @Autowired AccountRepository accounts;
  @Autowired SiteCatalogRepository sites;
  @Autowired InstallationService installations;
  @Autowired HistoricalDesignService designs;
  @Autowired HistoricalService history;
  @Autowired HistoricalSubmissionService submissions;
  @Autowired DisasterService disasters;
  @Autowired CostService costs;
  @Autowired JsonService json;
  @Autowired io.waterleague.budget.service.BudgetService budget;
  @MockitoSpyBean GamePriceCatalog prices;

  @Test
  void oldAndIndexedPricesSurviveMixedDesignCalculationSubmissionAndOriginalLedger()
      throws Exception {
    var previous = new AtomicBoolean(true);
    // 격리 시험에서만 이전 가격 공표 상태를 재현하고 저장 후 현재 공표 상태로 전환한다.
    doAnswer(
            call ->
                previous.get()
                    ? ((JsonNode) call.getArgument(0)).deepCopy()
                    : call.callRealMethod())
        .when(prices)
        .metadata(any());
    UUID owner = UUID.randomUUID();
    String username = "price_" + owner.toString().substring(0, 8);
    accounts.add(
        new Account(
            owner,
            username,
            "가격 버전 시험",
            "NOT_A_LOGIN",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            "11200",
            "AFFILIATED"));
    var a = NativeSiteFixtures.cell(sites, "11200", FacilityType.PERMEABLE_PAVEMENT, 0);
    var b = NativeSiteFixtures.cell(sites, "11200", FacilityType.PERMEABLE_PAVEMENT, 1);
    var oldInstall =
        installations.install(
            username,
            new InstallRequest(
                "11200", a.cellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.TEN));
    var oldCost = costs.active(oldInstall.id());
    assertThat(oldInstall.cost()).isEqualByComparingTo("1100000");
    var event =
        disasters.catalog().events().stream()
            .filter(e -> e.id().equals("seoul-20220808"))
            .findFirst()
            .orElseThrow();
    var region =
        event.regions().stream()
            .filter(r -> r.districtId().equals("11200"))
            .findFirst()
            .orElseThrow();
    Instant at = Instant.parse(region.start()).plusSeconds(137);
    var first =
        new HistoricalDesignRequest.Item(
            UUID.randomUUID(),
            "11200",
            a.cellId(),
            FacilityType.PERMEABLE_PAVEMENT,
            BigDecimal.TEN,
            at);
    var original =
        designs.save(
            owner,
            event.id(),
            new HistoricalDesignRequest(UUID.randomUUID(), 0, 137, List.of(first)));
    var oldRow = original.snapshot().path("placements").get(0);
    String guest = "price-test-" + UUID.randomUUID();
    var guestRequest =
        new GuestHistoricalRequest(
            UUID.randomUUID(),
            event.id(),
            "11200",
            List.of(
                new GuestHistoricalRequest.Item(
                    "11200",
                    new HistoricalRequest.Item(
                        a.cellId(),
                        FacilityType.PERMEABLE_PAVEMENT,
                        BigDecimal.TEN,
                        at,
                        a.modelHash()))));
    var guestJob = history.createGuest(guest, guestRequest);
    previous.set(false);
    assertThat(history.createGuest(guest, guestRequest).id()).isEqualTo(guestJob.id());
    var newInstall =
        installations.install(
            username,
            new InstallRequest(
                "11200", b.cellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.TEN));
    assertThat(newInstall.cost()).isEqualByComparingTo("1237330");
    assertThat(budget.view(owner).allocatedKrw()).isEqualByComparingTo("2337330");
    assertThat(costs.active(oldInstall.id())).isEqualTo(oldCost);
    var second =
        new HistoricalDesignRequest.Item(
            UUID.randomUUID(),
            "11200",
            b.cellId(),
            FacilityType.PERMEABLE_PAVEMENT,
            BigDecimal.TEN,
            at);
    var mixed =
        designs.save(
            owner,
            event.id(),
            new HistoricalDesignRequest(UUID.randomUUID(), 1, 137, List.of(first, second)));
    BigDecimal total = BigDecimal.ZERO;
    for (var row : mixed.snapshot().path("placements")) {
      total = total.add(row.path("cost").decimalValue());
      if (row.path("item").path("id").asString().equals(first.id().toString()))
        assertThat(row).isEqualTo(oldRow);
    }
    assertThat(total).isEqualByComparingTo("2337330");
    var request =
        new HistoricalRequest(
            UUID.randomUUID(),
            "11200",
            region.modelHash(),
            List.of(
                new HistoricalRequest.Item(
                    a.cellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.TEN, at, a.modelHash()),
                new HistoricalRequest.Item(
                    b.cellId(),
                    FacilityType.PERMEABLE_PAVEMENT,
                    BigDecimal.TEN,
                    at,
                    b.modelHash())),
            null,
            "INSTALLATION_TIME_EXPERIMENT_V1",
            null,
            mixed.revision(),
            event.id());
    var experiment = history.create(owner, request);
    var submitRequest =
        new HistoricalDesignSubmissionRequest(
            UUID.randomUUID(), mixed.revision(), mixed.snapshotSha256());
    var submission = submissions.submitSaved(owner, event.id(), submitRequest);
    assertThat(history.create(owner, request).id()).isEqualTo(experiment.id());
    assertThat(submissions.submitSaved(owner, event.id(), submitRequest).id())
        .isEqualTo(submission.id());
    assertThat(designs.revision(owner, event.id(), 1).snapshot()).isEqualTo(original.snapshot());
    var restored =
        costs.recordedSite(
            sites.require("11200", a.cellId()),
            FacilityType.PERMEABLE_PAVEMENT,
            BigDecimal.TEN,
            oldRow.path("costSnapshotRaw").asString(),
            oldRow.path("costSnapshotSha256").asString());
    assertThat(restored.unitCosts().get("PERMEABLE_PAVEMENT")).isEqualByComparingTo("110000");
    var six =
        prices.site(restored, "50f6e00757ecba3ed77a811b0fd9d03f72b800c0c47712093bf1adda99421036");
    var sixRecord =
        costs.snapshot(
            six, FacilityType.PERMEABLE_PAVEMENT, BigDecimal.TEN, new BigDecimal("1100000"));
    assertThat(
            costs
                .recordedSite(
                    restored,
                    FacilityType.PERMEABLE_PAVEMENT,
                    BigDecimal.TEN,
                    sixRecord.raw(),
                    sixRecord.sha256())
                .costSourceSha256())
        .isEqualTo(six.costSourceSha256());
    for (var field : List.of("unitCostKrw", "budgetChargeKrw", "costSourceSha256", "cellId")) {
      ObjectNode forged = (ObjectNode) json.tree(oldRow.path("costSnapshotRaw").asString());
      forged.put(field, field.endsWith("Krw") ? "1" : "0".repeat(64));
      String raw = json.write(forged);
      assertThatThrownBy(
              () ->
                  costs.recordedSite(
                      restored,
                      FacilityType.PERMEABLE_PAVEMENT,
                      BigDecimal.TEN,
                      raw,
                      json.hash(raw)))
          .isInstanceOf(io.waterleague.cost.exception.CostException.class);
    }
    ObjectNode precise = (ObjectNode) json.tree(oldRow.path("costSnapshotRaw").asString());
    precise.put("budgetChargeKrw", new BigDecimal("1100000.0000000000001"));
    String preciseRaw = json.write(precise);
    assertThatThrownBy(
            () ->
                costs.recordedSite(
                    restored,
                    FacilityType.PERMEABLE_PAVEMENT,
                    BigDecimal.TEN,
                    preciseRaw,
                    json.hash(preciseRaw)))
        .isInstanceOf(io.waterleague.cost.exception.CostException.class);
    var export = System.getProperty("waterleague.integration.prices.fixture");
    if (export != null)
      Files.writeString(
          Path.of(export),
          json.write(
              Map.of(
                  "ownerId",
                  owner,
                  "installations",
                  List.of(oldInstall.id(), newInstall.id()),
                  "experimentId",
                  experiment.id(),
                  "submissionId",
                  submission.id(),
                  "forcingHash",
                  region.modelHash(),
                  "design",
                  mixed,
                  "expectedTotalKrw",
                  2337330,
                  "currentSite",
                  sites.require("11200", b.cellId()),
                  "newCost",
                  costs.active(newInstall.id()),
                  "guestJobId",
                  guestJob.id())),
          StandardOpenOption.CREATE_NEW);
  }
}
