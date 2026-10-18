package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.installation.dto.*;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.service.*;
import io.waterleague.installation.view.SiteView;
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
class CisternMapPlanTests {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired AccountRepository accounts;
  @Autowired CisternPlanService service;
  @Autowired InstallationService installations;
  @Autowired io.waterleague.weekly.service.WeeklySeasonService seasons;
  @Autowired SiteCatalogRepository sites;
  @Autowired JdbcTemplate db;
  @Autowired io.waterleague.budget.service.BudgetService budget;
  @Autowired jakarta.validation.Validator validator;
  SiteView roof, ground;

  @BeforeEach
  void prepare() {
    db.update("DELETE FROM cistern_map_plans");
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM budget_ledger_entries");
    db.update("DELETE FROM shared_installations");
    var all = sites.district("2419953").values();
    roof =
        all.stream()
            .filter(s -> s.kind().equals("ROOF") && s.maxAreaM2().doubleValue() > 20)
            .findFirst()
            .orElseThrow();
    ground =
        all.stream()
            .filter(
                s ->
                    s.kind().equals("GROUND")
                        && s.existingInfrastructure() == null
                        && s.maxAreaM2().doubleValue() > 20)
            .findFirst()
            .orElseThrow();
  }

  Account account(String district) {
    UUID id = UUID.randomUUID();
    String name = "cistern_" + id.toString().substring(0, 8);
    var value =
        new Account(
            id,
            name,
            name,
            "NOT_A_LOGIN",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            district,
            "AFFILIATED");
    accounts.add(value);
    return value;
  }

  CisternPlanRequest request() {
    return new CisternPlanRequest(
        roof.districtId(),
        roof.cellId(),
        ground.cellId(),
        roof.modelHash(),
        ground.modelHash(),
        new BigDecimal("20"),
        BigDecimal.ONE,
        new BigDecimal("2.350"));
  }

  @Test
  void immutableSourceCostsIdempotencyAndNoSpending() {
    var owner = account("2419953");
    var before = budget.view(owner.id()).remainingKrw();
    var first = service.save(owner.username(), request());
    var again = service.save(owner.username(), request());
    assertThat(again.id()).isEqualTo(first.id());
    assertThat(service.list(owner.username())).hasSize(1);
    var s = first.snapshot();
    assertThat(s.path("capacityM3").decimalValue()).isEqualByComparingTo("2.35");
    assertThat(s.path("installationReady").asBoolean()).isFalse();
    assertThat(s.path("positionReserved").asBoolean()).isFalse();
    assertThat(s.path("roof").path("modelHash").asString()).isEqualTo(roof.modelHash());
    assertThat(
            s.path("referenceCosts")
                .path("items")
                .get(0)
                .path("quotes")
                .get(2)
                .path("quotedSubtotalKrw")
                .asLong())
        .isEqualTo(2857000);
    assertThat(s.path("referenceCosts").path("budgetChargedKrw").isNull()).isTrue();
    assertThat(installations.active()).isEmpty();
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo(before);
    assertThat(service.list(owner.username()).getFirst().snapshot()).isEqualTo(s);
  }

  @Test
  void ownerAndDistrictIsolationAndRevocation() {
    var owner = account("2419953");
    var other = account("2419953");
    var foreign = account("2419954");
    var first = service.save(owner.username(), request());
    assertThat(service.list(other.username())).isEmpty();
    assertThatThrownBy(() -> service.remove(other.username(), first.id()))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.save(foreign.username(), request()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.DISTRICT_ACCESS_DENIED));
    db.update("UPDATE accounts SET approval_status='SUSPENDED' WHERE id=?", owner.id());
    assertThatThrownBy(() -> service.list(owner.username())).isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.remove(owner.username(), first.id()))
        .isInstanceOf(DomainException.class);
    db.update("UPDATE accounts SET approval_status='APPROVED' WHERE id=?", owner.id());
    service.remove(owner.username(), first.id());
    assertThat(service.list(owner.username())).isEmpty();
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM cistern_map_plans WHERE deleted_at IS NOT NULL",
                Integer.class))
        .isEqualTo(1);
  }

  @Test
  void staleAreaOccupiedAndTamperedRecordsRejected() {
    var owner = account("2419953");
    var r = request();
    assertThatThrownBy(
            () ->
                service.save(
                    owner.username(),
                    new CisternPlanRequest(
                        r.districtId(),
                        r.roofCellId(),
                        r.groundCellId(),
                        "0".repeat(64),
                        r.groundModelHash(),
                        r.captureAreaM2(),
                        r.tankAreaM2(),
                        r.tankDepthM())))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.save(
                    owner.username(),
                    new CisternPlanRequest(
                        r.districtId(),
                        r.roofCellId(),
                        r.groundCellId(),
                        r.roofModelHash(),
                        r.groundModelHash(),
                        roof.maxAreaM2().add(BigDecimal.ONE),
                        r.tankAreaM2(),
                        r.tankDepthM())))
        .isInstanceOf(DomainException.class);
    assertThat(
            validator.validate(
                new CisternPlanRequest(
                    r.districtId(),
                    r.roofCellId(),
                    r.groundCellId(),
                    r.roofModelHash(),
                    r.groundModelHash(),
                    r.captureAreaM2(),
                    r.tankAreaM2(),
                    new BigDecimal("100.001"))))
        .isNotEmpty();
    var installed =
        installations.install(
            owner.username(),
            new InstallRequest(
                r.districtId(), r.groundCellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE));
    assertThatThrownBy(() -> service.save(owner.username(), r))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.SITE_OCCUPIED));
    seasons.closeOwnerAt(owner.id(), installed.seasonEndsAt());
    var first = service.save(owner.username(), r);
    db.update("UPDATE cistern_map_plans SET snapshot_text='{}' WHERE id=?", first.id());
    assertThatThrownBy(() -> service.list(owner.username()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.SPATIAL_DATA_INVALID));
  }

  @Test
  void geometryBindingPersistenceAndOldSnapshotPreservation() {
    var owner = account("2419953");
    var r = request();
    var old = service.save(owner.username(), r);
    assertThat(old.snapshot().path("request").has("tankLayout")).isFalse();
    var layout =
        new CisternLayoutRequest(
            BigDecimal.ONE,
            new BigDecimal("0.1"),
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO);
    var request =
        new CisternPlanRequest(
            r.districtId(),
            r.roofCellId(),
            r.groundCellId(),
            r.roofModelHash(),
            r.groundModelHash(),
            r.captureAreaM2(),
            r.tankAreaM2(),
            r.tankDepthM(),
            layout);
    var saved = service.save(owner.username(), request);
    assertThat(saved.snapshot().path("schemaVersion").asInt()).isEqualTo(2);
    assertThat(saved.snapshot().path("tankGeometry").path("outerWidthM").asDouble()).isEqualTo(1.2);
    assertThat(saved.snapshot().path("tankGeometry").path("sourceModelHash").asString())
        .isEqualTo(ground.modelHash());
    assertThat(service.save(owner.username(), request).id()).isEqualTo(saved.id());
    assertThat(
            service.list(owner.username()).stream()
                .filter(v -> v.id().equals(saved.id()))
                .findFirst()
                .orElseThrow()
                .snapshot())
        .isEqualTo(saved.snapshot());
    assertThat(service.save(owner.username(), r).inputHash()).isEqualTo(old.inputHash());
    var outside =
        new CisternLayoutRequest(
            new BigDecimal("10000"),
            new BigDecimal("0.1"),
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO);
    assertThatThrownBy(
            () ->
                service.save(
                    owner.username(),
                    new CisternPlanRequest(
                        r.districtId(),
                        r.roofCellId(),
                        r.groundCellId(),
                        r.roofModelHash(),
                        r.groundModelHash(),
                        r.captureAreaM2(),
                        r.tankAreaM2(),
                        r.tankDepthM(),
                        outside)))
        .isInstanceOf(DomainException.class);
    assertThat(installations.active()).isEmpty();
  }

  @Test
  void concurrentRetryCreatesOneDraft() throws Exception {
    var owner = account("2419953");
    var start = new CountDownLatch(1);
    try (var pool = Executors.newFixedThreadPool(2)) {
      Callable<UUID> action =
          () -> {
            start.await();
            return service.save(owner.username(), request()).id();
          };
      var a = pool.submit(action);
      var b = pool.submit(action);
      start.countDown();
      assertThat(a.get(20, TimeUnit.SECONDS)).isEqualTo(b.get(20, TimeUnit.SECONDS));
      assertThat(service.list(owner.username())).hasSize(1);
    }
  }
}
