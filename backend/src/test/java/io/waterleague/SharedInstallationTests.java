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
class SharedInstallationTests extends PostgresIntegrationTest {
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
  @Autowired io.waterleague.weekly.service.WeeklySeasonService seasons;
  @Autowired JdbcTemplate db;
  @Autowired io.waterleague.installation.repository.SiteCatalogRepository sites;
  @Autowired io.waterleague.budget.service.BudgetService budget;
  @Autowired io.waterleague.cost.service.CostService costs;
  @Autowired io.waterleague.common.service.JsonService json;

  @Test
  void streetPavementUsesImmutableSiteAreaCostAndOwnerRules() {
    var owner = account("11680");
    var page =
        service.sites(
            "11680",
            0,
            0,
            0,
            FacilityType.PERMEABLE_PAVEMENT,
            true,
            io.waterleague.installation.entity.SiteSurface.ROADWAY);
    assertThat(page.sites()).isNotEmpty();
    assertThat(page.sites()).allMatch(s -> s.allowedTypes().equals(List.of("PERMEABLE_PAVEMENT")));
    var site =
        page.sites().stream()
            .filter(s -> s.maxAreaM2().compareTo(BigDecimal.TEN) >= 0)
            .findFirst()
            .orElseThrow();

    assertThat(service.ground(site.center().get(0), site.center().get(1)).cellId())
        .isEqualTo(site.cellId());
    assertThatThrownBy(() -> service.ground(Double.NaN, 0)).isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.ground(99999, 99999)).isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        site.districtId(),
                        site.cellId(),
                        FacilityType.RAIN_GARDEN,
                        BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        site.districtId(),
                        site.cellId(),
                        FacilityType.PERMEABLE_PAVEMENT,
                        site.maxAreaM2().add(new BigDecimal("0.01")))))
        .isInstanceOf(DomainException.class);
    var outsider = account("11200");
    assertThatThrownBy(
            () ->
                service.install(
                    outsider.username(),
                    new InstallRequest(
                        site.districtId(),
                        site.cellId(),
                        FacilityType.PERMEABLE_PAVEMENT,
                        BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    var installed =
        service.install(
            owner.username(),
            new InstallRequest(
                site.districtId(), site.cellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.TEN));
    assertThat(installed.modelHash()).isEqualTo(site.modelHash());
    assertThat(installed.cost())
        .isEqualByComparingTo(site.unitCosts().get("PERMEABLE_PAVEMENT").multiply(BigDecimal.TEN));
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        site.districtId(),
                        site.cellId(),
                        FacilityType.PERMEABLE_PAVEMENT,
                        BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    var walkway =
        service.sites(
            "11680",
            0,
            0,
            0,
            FacilityType.PERMEABLE_PAVEMENT,
            true,
            io.waterleague.installation.entity.SiteSurface.WALKWAY);
    assertThat(walkway.sites()).isNotEmpty();
    assertThat(walkway.sites()).allMatch(s -> s.sourceRole().equals("SIDEWALK_AREA"));
  }

  @Test
  void swaleRejectsAreaOutsideFixedWidthDesignAndSharesBudget() {
    var owner = account("11680");
    var site =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
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
                        "11680",
                        site.cellId(),
                        FacilityType.VEGETATIVE_SWALE,
                        cap.add(new BigDecimal("0.01")))))
        .isInstanceOf(DomainException.class);
    var installed =
        service.install(
            owner.username(),
            new InstallRequest("11680", site.cellId(), FacilityType.VEGETATIVE_SWALE, cap));
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
                    owner.username(),
                    new InstallRequest(
                        "11680", site.cellId(), FacilityType.RAIN_GARDEN, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    var roof =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(s -> s.kind().equals("ROOF"))
            .findFirst()
            .orElseThrow();
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "11680", roof.cellId(), FacilityType.VEGETATIVE_SWALE, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void trenchRejectsAreaOutsideFixedWidthDesignAndSharesBudget() {
    var owner = account("11680");
    var site =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(
                s ->
                    s.allowedTypes().contains("INFILTRATION_TRENCH")
                        && s.existingInfrastructure() == null)
            .findFirst()
            .orElseThrow();
    var cap = site.maxAreaFor(FacilityType.INFILTRATION_TRENCH);
    assertThat(cap).isLessThan(site.maxAreaM2());
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "11680",
                        site.cellId(),
                        FacilityType.INFILTRATION_TRENCH,
                        cap.add(new BigDecimal("0.01")))))
        .isInstanceOf(DomainException.class);
    var installed =
        service.install(
            owner.username(),
            new InstallRequest("11680", site.cellId(), FacilityType.INFILTRATION_TRENCH, cap));
    var charge = cap.multiply(new BigDecimal("171429"));
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
                .path("sourceInitialCostKrw")
                .asLong())
        .isEqualTo(12000000L);
    assertThat(costs.active(installed.id()).estimate().path("priceBaseYear").isNull()).isTrue();
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "11680", site.cellId(), FacilityType.RAIN_GARDEN, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    var roof =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(s -> s.kind().equals("ROOF"))
            .findFirst()
            .orElseThrow();
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "11680", roof.cellId(), FacilityType.INFILTRATION_TRENCH, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void bioretentionUsesPublicSoilAndSharedBudgetWhileRejectingRoofAndDuplicate() {
    var owner = account("11680");
    var eligible =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(
                site ->
                    site.allowedTypes().contains("BIORETENTION")
                        && site.existingInfrastructure() == null)
            .findFirst()
            .orElseThrow();
    var roof =
        NativeSiteFixtures.sites(sites, "11680").values().stream()
            .filter(site -> site.kind().equals("ROOF"))
            .findFirst()
            .orElseThrow();
    assertThat(eligible.physicalInputs().path("soilStatus").asString())
        .isEqualTo("PUBLIC_REFERENCE_SCENARIO");
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "11680", roof.cellId(), FacilityType.BIORETENTION, BigDecimal.TEN)))
        .isInstanceOf(DomainException.class);
    var installed =
        service.install(
            owner.username(),
            new InstallRequest(
                "11680", eligible.cellId(), FacilityType.BIORETENTION, new BigDecimal("20")));
    assertThat(installed.cost()).isEqualByComparingTo("11200000");
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("1988800000");
    assertThat(budget.view(owner.id()).accounting().facilities())
        .hasSize(6)
        .allSatisfy(f -> assertThat(f.availableKrw()).isEqualByComparingTo("1988800000"));
    assertThat(costs.active(installed.id()).estimate().path("completeInstalledCostKrw").isNull())
        .isTrue();
    assertThatThrownBy(
            () ->
                service.install(
                    owner.username(),
                    new InstallRequest(
                        "11680", eligible.cellId(), FacilityType.BIORETENTION, BigDecimal.TEN)))
        .isInstanceOf(DomainException.class);
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
  }

  @Test
  void costEvidenceFreezesQuantitySourceAndUnknownCostsWithoutRetrofittingOldRecords() {
    var owner = account("11680");
    var installed =
        service.install(
            owner.username(),
            new InstallRequest(
                "11680",
                NativeSiteFixtures.cell(sites, "11680", FacilityType.PERMEABLE_PAVEMENT, 0)
                    .cellId(),
                FacilityType.PERMEABLE_PAVEMENT,
                new BigDecimal("20.25")));
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
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
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

  @Test
  void mapReturnsServerScoreAndObservationTimeForEachInstallation() {
    var owner = account("11680");
    var installed = service.install(owner.username(), placement("11680"));
    var before = service.activeViews();
    assertThat(before).hasSize(1);
    assertThat(before.getFirst().scoreM3()).isNull();
    var through = installed.installedAt().plusSeconds(1);
    var job = UUID.randomUUID();
    db.update(
        """
        INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,state,lease_token,created_at,finished_at,input_hash,result)
        VALUES(?,?,?,?,'SUCCEEDED',?,?,?,?,'{}')
        """,
        job,
        installed.id(),
        java.sql.Timestamp.from(installed.installedAt()),
        java.sql.Timestamp.from(through),
        UUID.randomUUID(),
        java.sql.Timestamp.from(through),
        java.sql.Timestamp.from(through),
        "a".repeat(64));
    var week =
        installed
            .installedAt()
            .atZone(java.time.ZoneId.of("Asia/Seoul"))
            .toLocalDate()
            .with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY));
    db.update(
        """
        INSERT INTO shared_weekly_scores(installation_id,week_start,score_m3,evaluated_minutes,evaluated_seconds,evaluated_through,source_job_id,rule_version)
        VALUES(?,?,1.25,1,1,?,?,'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2')
        """,
        installed.id(),
        java.sql.Date.valueOf(week),
        java.sql.Timestamp.from(through),
        job);
    var scored = service.activeViews().getFirst();
    assertThat(scored.ownerId()).isEqualTo(owner.id());
    assertThat(scored.scoreM3()).isEqualByComparingTo("1.25");
    assertThat(scored.evaluatedThrough()).isEqualTo(through);
    assertThat(scored.center()).isEqualTo(before.getFirst().center());
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
        district,
        NativeSiteFixtures.cell(sites, district, FacilityType.PERMEABLE_PAVEMENT, 0).cellId(),
        FacilityType.PERMEABLE_PAVEMENT,
        new BigDecimal("20.00"));
  }

  @Test
  void publicPointReferenceDoesNotInventFootprintOrConstructionApproval() throws Exception {
    var reference = NativeSiteFixtures.reference(sites);
    var owner = account(reference.districtId());
    assertThat(reference.referenceInfrastructure().path("references")).isNotEmpty();
    assertThat(reference.existingInfrastructure()).isNull();
    assertThat(reference.siteEligibility()).isEqualTo("UNKNOWN");
    var installed =
        service.install(
            owner.username(),
            new InstallRequest(
                reference.districtId(),
                reference.cellId(),
                FacilityType.PERMEABLE_PAVEMENT,
                BigDecimal.TEN));
    assertThat(installed.modelHash()).isEqualTo(reference.modelHash());
    assertThat(budget.view(owner.id()).allocatedKrw()).isEqualByComparingTo(installed.cost());
  }

  @Test
  void oldGeometryIdentifiersCannotAllocateBudgetOrResolveToNativeCandidates() {
    var owner = account("11200");
    for (var old : List.of("RW653831038", "G20695-54482", "R1")) {
      assertThatThrownBy(
              () ->
                  service.install(
                      owner.username(),
                      new InstallRequest("11200", old, FacilityType.GREEN_ROOF, BigDecimal.TEN)))
          .isInstanceOf(DomainException.class);
    }
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    assertThat(db.queryForObject("SELECT COUNT(*) FROM budget_ledger_entries", Integer.class))
        .isZero();
  }

  @Test
  void existingMembersChooseOnceAndCannotInstallElsewhere() {
    var a = account(null);
    assertThatThrownBy(() -> service.install(a.username(), placement("11680")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.DISTRICT_REQUIRED));
    var updated =
        auth.selectDistrict(a.username(), new DistrictSelectionRequest("11680", "AFFILIATED"));
    assertThat(updated.districtId()).isEqualTo("11680");
    assertThatThrownBy(
            () ->
                auth.selectDistrict(
                    a.username(), new DistrictSelectionRequest("11590", "RESIDENT")))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.install(a.username(), placement("11590")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.DISTRICT_ACCESS_DENIED));
    assertThat(service.active()).isEmpty();
  }

  @Test
  void membersCanShareLocationWhileOwnDuplicateAndSeasonRemovalAreRejected() throws Exception {
    var a = account("11680");
    var b = account("11680");
    var start = new CountDownLatch(1);
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<Future<String>>();
      for (var actor : List.of(a, b))
        futures.add(
            executor.submit(
                () -> {
                  start.await();
                  try {
                    service.install(actor.username(), placement("11680"));
                    return "INSTALLED";
                  } catch (DomainException e) {
                    return e.code().name();
                  }
                }));
      start.countDown();
      var outcomes = new ArrayList<String>();
      for (var f : futures) outcomes.add(f.get(10, TimeUnit.SECONDS));
      assertThat(outcomes).containsExactlyInAnyOrder("INSTALLED", "INSTALLED");
    }
    var installed = service.active().getFirst();
    assertThat(service.active()).hasSize(2);
    assertThat(installed.cost()).isEqualByComparingTo("2200000");
    assertThat(installed.installedAt().getNano()).isZero();
    assertThat(
            db.queryForObject(
                "SELECT physics_policy FROM shared_installations WHERE id=?",
                String.class,
                installed.id()))
        .isEqualTo("INSTALLATION_SECOND_V2");
    var owner = installed.ownerId().equals(a.id()) ? a : b;
    var other = owner.id().equals(a.id()) ? b : a;
    assertThatThrownBy(() -> service.remove(other.username(), installed.id()))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.remove(owner.username(), installed.id()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e ->
                assertThat(e.code())
                    .isEqualTo(
                        io.waterleague.common.exception.ErrorCode.SEASON_INSTALLATION_LOCKED));
    assertThatThrownBy(() -> service.install(owner.username(), placement("11680")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e ->
                assertThat(e.code())
                    .isEqualTo(io.waterleague.common.exception.ErrorCode.SITE_OCCUPIED));
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt().minusNanos(1));
    assertThat(service.active()).hasSize(2);
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
    assertThat(service.active()).hasSize(1);
    assertThat(service.active().getFirst().ownerId()).isEqualTo(other.id());
    assertThat(budget.history(owner.id(), null).entries()).hasSize(2);
    assertThat(budget.history(owner.id(), null).entries().getFirst().effectiveAt())
        .isEqualTo(installed.seasonEndsAt());
    assertThat(
            db.queryForObject(
                    "SELECT removed_at FROM shared_installations WHERE id=?",
                    java.sql.Timestamp.class,
                    installed.id())
                .toInstant())
        .isEqualTo(installed.seasonEndsAt());
    assertThat(budget.view(owner.id()).allocatedKrw()).isZero();
    assertThat(budget.view(other.id()).allocatedKrw()).isEqualByComparingTo("2200000");
  }

  @Test
  void oneMemberConcurrentSameSiteHasOneAllocation() throws Exception {
    var a = account("11680");
    // 원형 후보의 최초 조회를 끝낸 뒤 같은 설치 요청의 경합만 측정한다.
    var request = placement("11680");
    var start = new CountDownLatch(1);
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<Future<String>>();
      for (int n = 0; n < 2; n++)
        futures.add(
            executor.submit(
                () -> {
                  start.await();
                  try {
                    service.install(a.username(), request);
                    return "INSTALLED";
                  } catch (DomainException e) {
                    return e.code().name();
                  }
                }));
      start.countDown();
      assertThat(
              List.of(
                  futures.get(0).get(10, TimeUnit.SECONDS),
                  futures.get(1).get(10, TimeUnit.SECONDS)))
          .containsExactlyInAnyOrder("INSTALLED", "SITE_OCCUPIED");
    }
    assertThat(service.active()).hasSize(1);
    assertThat(budget.history(a.id(), null).entries()).hasSize(1);
  }

  @Test
  void personalBudgetSerializesConcurrentSpendingAndIsolatesMembers() throws Exception {
    String district = "11680";
    var owner = account(district);
    var other = account(district);
    // 실제 서버 설치로 한도 직전까지 배정하고 서로 다른 시설의 경합을 검사한다.
    var remainingArea = new BigDecimal("5705");
    for (var site :
        NativeSiteFixtures.sites(sites, district).values().stream()
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
      for (String cell :
          List.of(
              NativeSiteFixtures.cell(sites, district, FacilityType.PERMEABLE_PAVEMENT, 1).cellId(),
              NativeSiteFixtures.cell(sites, district, FacilityType.PERMEABLE_PAVEMENT, 2)
                  .cellId())) {
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
                district,
                NativeSiteFixtures.cell(sites, district, FacilityType.PERMEABLE_PAVEMENT, 3)
                    .cellId(),
                FacilityType.PERMEABLE_PAVEMENT,
                new BigDecimal("20")));
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
        .contains("seoul-native-infrastructure-20261020-v1", "historicalExistenceVerified");
    seasons.closeOwnerAt(other.id(), independent.seasonEndsAt());
    assertThat(budget.view(other.id()).remainingKrw()).isEqualByComparingTo("2000000000");
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo("1050000");
  }

  @Test
  void rejectsUnknownSitesAndInvalidAreaAndPreservesGlobalCoordinates() {
    var a = account("11680");
    var reference = NativeSiteFixtures.cell(sites, "11680", FacilityType.PERMEABLE_PAVEMENT, 0);
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
                        "11680", "G99", FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.install(
                    a.username(),
                    new InstallRequest(
                        "11680", reference.cellId(), FacilityType.GREEN_ROOF, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.install(
                    a.username(),
                    new InstallRequest(
                        "11680",
                        NativeSiteFixtures.cell(sites, "11680", FacilityType.PERMEABLE_PAVEMENT, 0)
                            .cellId(),
                        FacilityType.PERMEABLE_PAVEMENT,
                        reference.maxAreaM2().add(new BigDecimal("0.01")))))
        .isInstanceOf(DomainException.class);
    var overview = service.sites(null, 0, 0, 0, null, false);
    assertThat(overview.districtCounts()).hasSize(25);
    assertThat(overview.districtCounts().values().stream().mapToInt(Integer::intValue).sum())
        .isEqualTo(1022710);
    var page = service.sites("11680", 7239.5, -7741.5, 0, null, false);
    assertThat(page.sites()).hasSize(200);
    assertThat(page.matchedCount()).isGreaterThan(1000);
    var site = page.sites().getFirst();
    assertThat(service.site(site.districtId(), site.cellId()).polygons())
        .isEqualTo(site.polygons());
    assertThat(service.active()).isEmpty();
  }

  @Test
  void expandedSitesUseFrozenCatalogAndShareBudgetAndOccupancy() {
    var a = account("11680");
    var page = service.sites("11680", 7239.5, -7741.5, 0, FacilityType.GREEN_ROOF, true);
    var site = page.sites().stream().filter(s -> s.kind().equals("ROOF")).findFirst().orElseThrow();
    var installed =
        service.install(
            a.username(),
            new InstallRequest(
                site.districtId(), site.cellId(), FacilityType.GREEN_ROOF, BigDecimal.TEN));
    assertThat(installed.modelHash()).isEqualTo(site.modelHash());
    assertThat(service.building(site.districtId(), site.sourceIds().getFirst()).cellId())
        .isEqualTo(site.cellId());
    assertThatThrownBy(() -> service.site("11680", "R1")).isInstanceOf(DomainException.class);
    assertThat(service.view(installed).center()).isEqualTo(site.center());
    assertThat(
            service
                .sites("11680", 7239.5, -7741.5, 0, FacilityType.GREEN_ROOF, true)
                .matchedCount())
        .isEqualTo(page.matchedCount());
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
    assertThatThrownBy(() -> service.sites("11680", Double.NaN, 0, 0, null, false))
        .isInstanceOf(DomainException.class);
  }
}
