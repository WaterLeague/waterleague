package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.dto.DistrictSelectionRequest;
import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.exception.*;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class SharedInstallationTests {
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

  @Autowired AccountRepository accounts;
  @Autowired AccountService auth;
  @Autowired InstallationService service;
  @Autowired JdbcTemplate db;
  @Autowired io.waterleague.installation.repository.SiteCatalogRepository sites;
  @Autowired io.waterleague.budget.service.BudgetService budget;
  @Autowired io.waterleague.cost.service.CostService costs;
  @Autowired io.waterleague.common.service.JsonService json;

  @Test
  void swaleRejectsAreaOutsideFixedWidthDesignAndSharesBudget() {
    var owner = account("2410520");
    var site =
        sites.district("2410520").values().stream()
            .filter(
                s ->
                    s.allowedTypes().contains("VEGETATIVE_SWALE")
                        && s.existingInfrastructure() == null)
            .findFirst()
            .orElseThrow();
    var cap = site.maxAreaFor(FacilityType.VEGETATIVE_SWALE);
    assertThat(cap).isLessThan(site.maxAreaM2());
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "2410520",
                        site.cellId(),
                        FacilityType.VEGETATIVE_SWALE,
                        cap.add(new BigDecimal("0.01")))))
        .isInstanceOf(DomainException.class);
    var installed =
        service.install(
            owner.username(),
            new InstallRequest("2410520", site.cellId(), FacilityType.VEGETATIVE_SWALE, cap));
    var charge = cap.multiply(new BigDecimal("45000"));
    assertThat(installed.cost()).isEqualByComparingTo(charge);
    assertThat(budget.view(owner.id()).remainingKrw())
        .isEqualByComparingTo(budget.limit().subtract(charge));
    assertThat(budget.view(owner.id()).accounting().programs()).hasSize(1);
    assertThat(
            costs
                .active(installed.id())
                .estimate()
                .path("source")
                .path("derivation")
                .path("headerUnitConflict")
                .asBoolean())
        .isTrue();
    assertThatThrownBy(
            () ->
                service.install(
                    account("2410520").username(),
                    new InstallRequest(
                        "2410520", site.cellId(), FacilityType.RAIN_GARDEN, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    service.remove(owner.username(), installed.id());
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    var roof =
        sites.district("2410520").values().stream()
            .filter(s -> s.kind().equals("ROOF"))
            .findFirst()
            .orElseThrow();
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "2410520", roof.cellId(), FacilityType.VEGETATIVE_SWALE, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void bioretentionUsesPublicSoilAndSharedBudgetWhileRejectingRoofAndDuplicate() {
    var owner = account("2410520");
    var eligible =
        sites.district("2410520").values().stream()
            .filter(
                site ->
                    site.allowedTypes().contains("BIORETENTION")
                        && site.existingInfrastructure() == null)
            .findFirst()
            .orElseThrow();
    var roof =
        sites.district("2410520").values().stream()
            .filter(site -> site.kind().equals("ROOF"))
            .findFirst()
            .orElseThrow();
    assertThat(eligible.physicalInputs().path("soilStatus").asString())
        .isEqualTo("TEXTURE_CLASS_LITERATURE_ESTIMATE");
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "2410520", roof.cellId(), FacilityType.BIORETENTION, BigDecimal.TEN)))
        .isInstanceOf(DomainException.class);
    var installed =
        service.install(
            owner.username(),
            new InstallRequest(
                "2410520", eligible.cellId(), FacilityType.BIORETENTION, new BigDecimal("20")));
    assertThat(installed.cost()).isEqualByComparingTo("11200000");
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("1988800000");
    assertThat(budget.view(owner.id()).accounting().facilities())
        .hasSize(5)
        .allSatisfy(f -> assertThat(f.availableKrw()).isEqualByComparingTo("1988800000"));
    assertThat(costs.active(installed.id()).estimate().path("completeInstalledCostKrw").isNull())
        .isTrue();
    assertThatThrownBy(
            () ->
                service.install(
                    account("2410520").username(),
                    new InstallRequest(
                        "2410520", eligible.cellId(), FacilityType.BIORETENTION, BigDecimal.TEN)))
        .isInstanceOf(DomainException.class);
    service.remove(owner.username(), installed.id());
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
  }

  @Test
  void costEvidenceFreezesQuantitySourceAndUnknownCostsWithoutRetrofittingOldRecords() {
    var owner = account("2410520");
    var installed =
        service.install(
            owner.username(),
            new InstallRequest(
                "2410520", "G1", FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("20.25")));
    var record = costs.active(installed.id());
    assertThat(record.status()).isEqualTo("RECORDED");
    var value = record.estimate();
    assertThat(value.path("budgetChargeKrw").decimalValue()).isEqualByComparingTo("2227500");
    assertThat(value.path("lines").get(0).path("quantity").decimalValue())
        .isEqualByComparingTo("20.25");
    assertThat(value.path("source").path("referenceYear").intValue()).isEqualTo(2022);
    assertThat(value.path("source").path("sourceSha256").asString())
        .isEqualTo("0efc54c3c884441d810ce28abb8928d758d98eb152fb71aac38791327b2d7414");
    assertThat(value.path("completeInstalledCostKrw").isNull()).isTrue();
    assertThat(value.path("historicalPriceEligible").asBoolean()).isFalse();
    for (var row : value.path("unpricedItems")) assertThat(row.path("amountKrw").isNull()).isTrue();
    String raw =
        db.queryForObject(
            "SELECT cost_snapshot FROM shared_installations WHERE id=?",
            String.class,
            installed.id());
    assertThat(record.sha256()).isEqualTo(json.hash(raw));
    db.update(
        "UPDATE shared_installations SET cost_snapshot=? WHERE id=?",
        raw.replace("2227500", "1"),
        installed.id());
    assertThatThrownBy(() -> costs.active(installed.id()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.COST_DATA_INVALID));
    db.update(
        "UPDATE shared_installations SET cost_snapshot=NULL,cost_snapshot_sha256=NULL WHERE id=?",
        installed.id());
    assertThat(costs.active(installed.id()).status()).isEqualTo("NOT_RECORDED");
    db.update(
        "UPDATE shared_installations SET cost_snapshot=?,cost_snapshot_sha256=? WHERE id=?",
        raw,
        record.sha256(),
        installed.id());
    service.remove(owner.username(), installed.id());
    assertThatThrownBy(() -> costs.active(installed.id()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    assertThat(
            db.queryForObject(
                "SELECT cost_snapshot FROM shared_installations WHERE id=?",
                String.class,
                installed.id()))
        .isEqualTo(raw);
  }

  @BeforeEach
  void clear() {
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM budget_ledger_entries");
    db.update("DELETE FROM shared_installations");
  }

  Account account(String district) {
    UUID id = UUID.randomUUID();
    String name = "shared_" + id.toString().substring(0, 8);
    var a =
        new Account(
            id,
            name,
            name,
            "not-used-by-test",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            district,
            district == null ? null : "AFFILIATED");
    accounts.add(a);
    return a;
  }

  InstallRequest placement(String district) {
    return new InstallRequest(
        district, "G1", FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("20.00"));
  }

  @Test
  void mappedGroundExclusionRejectsBeforeSpendingAndVacantFilterUsesSameRule() {
    String district = "2419954";
    var owner = account(district);
    var blocked = service.site(district, "G20695-54482");
    assertThat(blocked.existingInfrastructure().path("assets").get(0).path("assetName").asString())
        .isEqualTo("잠실유수지");
    assertThat(
            sites.district(district).values().stream()
                .filter(s -> s.existingInfrastructure() != null)
                .count())
        .isEqualTo(86);
    assertThat(sites.district(district).values().stream().filter(s -> s.kind().equals("ROOF")))
        .allMatch(s -> s.existingInfrastructure() == null);
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        district,
                        blocked.cellId(),
                        FacilityType.PERMEABLE_PAVEMENT,
                        BigDecimal.ONE)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.EXISTING_INFRASTRUCTURE));
    assertThat(service.active()).isEmpty();
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    assertThat(db.queryForObject("SELECT COUNT(*) FROM budget_ledger_entries", Integer.class))
        .isZero();
    var all =
        service.sites(district, blocked.center().get(0), blocked.center().get(1), 0, null, false);
    var vacant =
        service.sites(district, blocked.center().get(0), blocked.center().get(1), 0, null, true);
    assertThat(all.matchedCount() - vacant.matchedCount()).isEqualTo(86);
    assertThat(vacant.sites()).allMatch(s -> s.existingInfrastructure() == null);
  }

  @Test
  void existingMembersChooseOnceAndCannotInstallElsewhere() {
    var a = account(null);
    assertThatThrownBy(() -> service.install(a.username(), placement("2410520")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.DISTRICT_REQUIRED));
    var updated =
        auth.selectDistrict(a.username(), new DistrictSelectionRequest("2410520", "AFFILIATED"));
    assertThat(updated.districtId()).isEqualTo("2410520");
    assertThatThrownBy(
            () ->
                auth.selectDistrict(
                    a.username(), new DistrictSelectionRequest("2414774", "RESIDENT")))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.install(a.username(), placement("2414774")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.DISTRICT_ACCESS_DENIED));
    assertThat(service.active()).isEmpty();
  }

  @Test
  void sharedLocationHasExactlyOneWinnerUnderConcurrentRequests() throws Exception {
    var a = account("2410520");
    var b = account("2410520");
    var start = new CountDownLatch(1);
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<Future<String>>();
      for (var actor : List.of(a, b))
        futures.add(
            executor.submit(
                () -> {
                  start.await();
                  try {
                    service.install(actor.username(), placement("2410520"));
                    return "INSTALLED";
                  } catch (DomainException e) {
                    return e.code().name();
                  }
                }));
      start.countDown();
      var outcomes = new ArrayList<String>();
      for (var f : futures) outcomes.add(f.get(10, TimeUnit.SECONDS));
      assertThat(outcomes).containsExactlyInAnyOrder("INSTALLED", "SITE_OCCUPIED");
    }
    var installed = service.active().getFirst();
    assertThat(service.active()).hasSize(1);
    assertThat(installed.cost()).isEqualByComparingTo("2200000");
    var owner = installed.ownerId().equals(a.id()) ? a : b;
    var other = owner.id().equals(a.id()) ? b : a;
    assertThatThrownBy(() -> service.remove(other.username(), installed.id()))
        .isInstanceOf(DomainException.class);
    service.remove(owner.username(), installed.id());
    assertThat(service.active()).isEmpty();
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM shared_installations WHERE removed_at IS NOT NULL",
                Integer.class))
        .isEqualTo(1);
    service.install(other.username(), placement("2410520"));
    assertThat(service.active().getFirst().ownerId()).isEqualTo(other.id());
  }

  @Test
  void personalBudgetSerializesConcurrentSpendingAndIsolatesMembers() throws Exception {
    String district = "2410520";
    var owner = account(district);
    var other = account(district);
    // 실제 서버 설치로 한도 직전까지 배정하고 서로 다른 시설의 경합을 검사한다.
    var remainingArea = new BigDecimal("5705");
    for (var site :
        sites.district(district).values().stream()
            .filter(s -> s.allowedTypes().contains("GREEN_ROOF"))
            .sorted(Comparator.comparing(io.waterleague.installation.view.SiteView::cellId))
            .toList()) {
      var area = remainingArea.min(site.maxAreaM2().setScale(2, java.math.RoundingMode.DOWN));
      service.install(
          owner.username(),
          new InstallRequest(district, site.cellId(), FacilityType.GREEN_ROOF, area));
      remainingArea = remainingArea.subtract(area);
      if (remainingArea.signum() == 0) break;
    }
    assertThat(remainingArea).isZero();
    var start = new CountDownLatch(1);
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<Future<String>>();
      for (String cell : List.of("G2", "G3")) {
        futures.add(
            executor.submit(
                () -> {
                  start.await();
                  try {
                    service.install(
                        owner.username(),
                        new InstallRequest(
                            district, cell, FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("20")));
                    return "INSTALLED";
                  } catch (DomainException e) {
                    return e.code().name();
                  }
                }));
      }
      start.countDown();
      var outcomes = new ArrayList<String>();
      for (var f : futures) outcomes.add(f.get(10, TimeUnit.SECONDS));
      assertThat(outcomes).containsExactlyInAnyOrder("INSTALLED", "BUDGET_EXCEEDED");
    }
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("1050000");
    assertThat(budget.view(other.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    var independent =
        service.install(
            other.username(),
            new InstallRequest(
                district, "G4", FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("20")));
    assertThat(budget.view(other.id()).remainingKrw()).isEqualByComparingTo("1997800000");
    assertThat(budget.view(null).personal()).isFalse();
    assertThat(budget.view(null).allocatedKrw()).isZero();
    assertThat(
            db.queryForObject(
                "SELECT budget_policy FROM shared_installations WHERE id=?",
                String.class,
                independent.id()))
        .contains("SEOUL_PERSONAL_FULL_2026_V3");
    assertThat(
            db.queryForObject(
                "SELECT admission_snapshot FROM shared_installations WHERE id=?",
                String.class,
                independent.id()))
        .contains("seoul-basin-footprints-20261018-v3", "historicalExistenceVerified");
    service.remove(other.username(), independent.id());
    assertThat(budget.view(other.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("1050000");
  }

  @Test
  void rejectsUnknownSitesAndInvalidAreaAndPreservesGlobalCoordinates() {
    var a = account("2410520");
    var reference = service.site("2410520", "G1");
    assertThat(reference.unitCosts().get("GREEN_ROOF")).isEqualByComparingTo("350000");
    assertThat(
            reference
                .costModel()
                .path("facilities")
                .path("GREEN_ROOF")
                .path("referenceYear")
                .asInt())
        .isEqualTo(2025);
    assertThatThrownBy(
            () ->
                service.install(
                    a.username(),
                    new InstallRequest(
                        "2410520", "G99", FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.install(
                    a.username(),
                    new InstallRequest("2410520", "G1", FacilityType.GREEN_ROOF, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.install(
                    a.username(),
                    new InstallRequest(
                        "2410520", "G1", FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("25.01"))))
        .isInstanceOf(DomainException.class);
    var overview = service.sites(null, 0, 0, 0, null, false);
    assertThat(overview.districtCounts()).hasSize(25);
    assertThat(overview.districtCounts().values().stream().mapToInt(Integer::intValue).sum())
        .isEqualTo(154784);
    var page = service.sites("2410520", 7239.5, -7741.5, 0, null, false);
    assertThat(page.sites()).hasSize(200);
    assertThat(page.matchedCount()).isGreaterThan(1000);
    var site = service.site("2410520", "G5");
    assertThat(site.center()).containsExactly(7239.5, -7741.5);
    assertThat(service.active()).isEmpty();
  }

  @Test
  void expandedSitesUseFrozenCatalogAndShareBudgetAndOccupancy() {
    var a = account("2410520");
    var page = service.sites("2410520", 7239.5, -7741.5, 0, FacilityType.GREEN_ROOF, true);
    var site =
        page.sites().stream().filter(s -> s.cellId().startsWith("RW")).findFirst().orElseThrow();
    var installed =
        service.install(
            a.username(),
            new InstallRequest(
                site.districtId(), site.cellId(), FacilityType.GREEN_ROOF, BigDecimal.TEN));
    assertThat(installed.modelHash()).isEqualTo(site.modelHash());
    assertThat(service.building(site.districtId(), site.sourceIds().getFirst()).cellId())
        .isEqualTo(site.cellId());
    var legacy = service.site("2410520", "R1");
    assertThat(service.building(legacy.districtId(), legacy.sourceIds().getFirst()).cellId())
        .isEqualTo("R1");
    assertThat(service.view(installed).center()).isEqualTo(site.center());
    assertThat(
            service
                .sites("2410520", 7239.5, -7741.5, 0, FacilityType.GREEN_ROOF, true)
                .matchedCount())
        .isEqualTo(page.matchedCount() - 1);
    assertThatThrownBy(
            () ->
                service.install(
                    a.username(),
                    new InstallRequest(
                        site.districtId(),
                        site.cellId(),
                        FacilityType.RAIN_GARDEN,
                        BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.sites("2410520", Double.NaN, 0, 0, null, false))
        .isInstanceOf(DomainException.class);
  }
}
