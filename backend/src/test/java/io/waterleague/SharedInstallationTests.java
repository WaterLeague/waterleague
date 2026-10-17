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

  @BeforeEach
  void clear() {
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
  void rejectsUnknownSitesAndInvalidAreaAndPreservesGlobalCoordinates() {
    var a = account("2410520");
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
                        "2410520", "G1", FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("20.01"))))
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
