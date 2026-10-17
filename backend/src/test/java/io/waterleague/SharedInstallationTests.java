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

  @BeforeEach
  void clear() {
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
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
  void concurrentMembersShareDistrictBudgetWithoutSpendingOtherDistricts() throws Exception {
    String district = "2410520";
    var roofs =
        sites.district(district).values().stream()
            .filter(
                v ->
                    v.allowedTypes().contains("GREEN_ROOF")
                        && v.maxAreaM2().compareTo(new BigDecimal("100")) >= 0)
            .limit(3)
            .toList();
    assertThat(roofs).hasSize(3);
    var actors = List.of(account(district), account(district), account(district));
    var start = new CountDownLatch(1);
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<Future<String>>();
      for (int i = 0; i < 3; i++) {
        final int index = i;
        futures.add(
            executor.submit(
                () -> {
                  start.await();
                  try {
                    service.install(
                        actors.get(index).username(),
                        new InstallRequest(
                            district,
                            roofs.get(index).cellId(),
                            FacilityType.GREEN_ROOF,
                            new BigDecimal("100")));
                    return "INSTALLED";
                  } catch (DomainException e) {
                    return e.code().name();
                  }
                }));
      }
      start.countDown();
      var outcomes = new ArrayList<String>();
      for (var f : futures) outcomes.add(f.get(10, TimeUnit.SECONDS));
      assertThat(outcomes).containsExactlyInAnyOrder("INSTALLED", "INSTALLED", "BUDGET_EXCEEDED");
    }
    assertThat(budget.view().allocatedKrw()).isEqualByComparingTo("70000000");
    assertThat(budget.view().remainingKrw()).isEqualByComparingTo("1930000000");
    var row =
        budget.view().districts().stream()
            .filter(d -> d.districtId().equals(district))
            .findFirst()
            .orElseThrow();
    assertThat(row.remainingKrw()).isEqualByComparingTo("10000000");
    assertThat(budget.view().districts()).hasSize(25);
    assertThat(budget.view().districts().stream().filter(d -> !d.districtId().equals(district)))
        .allSatisfy(d -> assertThat(d.remainingKrw()).isEqualByComparingTo("80000000"));
    var other = account("2414774");
    service.install(other.username(), placement("2414774"));
    assertThat(
            budget.view().districts().stream()
                .filter(d -> d.districtId().equals("2414774"))
                .findFirst()
                .orElseThrow()
                .remainingKrw())
        .isEqualByComparingTo("77800000");
    var installed =
        service.active().stream()
            .filter(i -> i.districtId().equals(district))
            .findFirst()
            .orElseThrow();
    assertThat(
            db.queryForObject(
                "SELECT budget_policy FROM shared_installations WHERE id=?",
                String.class,
                installed.id()))
        .contains("SEOUL_DISTRICT_EQUAL_2026_V2");
    var owner =
        actors.stream().filter(a -> a.id().equals(installed.ownerId())).findFirst().orElseThrow();
    service.remove(owner.username(), installed.id());
    assertThat(
            budget.view().districts().stream()
                .filter(d -> d.districtId().equals(district))
                .findFirst()
                .orElseThrow()
                .remainingKrw())
        .isEqualByComparingTo("45000000");
    assertThat(budget.view().remainingKrw()).isEqualByComparingTo("1962800000");
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
