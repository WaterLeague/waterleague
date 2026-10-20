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
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class CisternMapPlanTests extends PostgresIntegrationTest {
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
  @Autowired io.waterleague.common.service.JsonService json;
  @Autowired org.springframework.security.crypto.password.PasswordEncoder passwords;

  @org.springframework.beans.factory.annotation.Value("${local.server.port}")
  int port;

  SiteView roof, ground;

  @BeforeEach
  void prepare() {
    db.update("DELETE FROM cistern_map_plans");
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM budget_ledger_entries");
    db.update("DELETE FROM shared_installations");
    var all = NativeSiteFixtures.sites(sites, "11200").values();
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
            district == null ? null : "AFFILIATED");
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

  CisternPlanRequest mode(CisternPlanRequest r, String mode) {
    return new CisternPlanRequest(
        r.districtId(),
        r.roofCellId(),
        r.groundCellId(),
        r.roofModelHash(),
        r.groundModelHash(),
        r.captureAreaM2(),
        r.tankAreaM2(),
        r.tankDepthM(),
        r.tankLayout(),
        r.equipment(),
        mode);
  }

  @Test
  void historicalPlansAllowForeignAndUnaffiliatedMembersWithoutSharingWeeklyOccupancy() {
    var owner = account("11200");
    var foreign = account("11710");
    var unaffiliated = account(null);
    var r = request();
    var weekly = service.save(owner.username(), r);
    assertThat(service.save(owner.username(), mode(r, "WEEKLY")).id()).isEqualTo(weekly.id());
    var installed =
        installations.install(
            owner.username(),
            new InstallRequest(
                r.districtId(),
                r.groundCellId(),
                FacilityType.valueOf(ground.allowedTypes().getFirst()),
                BigDecimal.ONE));
    for (var member : List.of(foreign, unaffiliated)) {
      var before = budget.view(member.id()).remainingKrw();
      assertThatThrownBy(() -> service.save(member.username(), r))
          .isInstanceOf(DomainException.class);
      var historical = service.save(member.username(), mode(r, "HISTORICAL"));
      assertThat(historical.snapshot().path("request").path("mode").asString())
          .isEqualTo("HISTORICAL");
      assertThat(historical.snapshot().path("installationReady").asBoolean()).isFalse();
      assertThat(service.save(member.username(), mode(r, "HISTORICAL")).id())
          .isEqualTo(historical.id());
      assertThat(budget.view(member.id()).remainingKrw()).isEqualByComparingTo(before);
      assertThat(service.list(member.username())).hasSize(1);
      assertThatThrownBy(
              () ->
                  installations.install(
                      member.username(),
                      new InstallRequest(
                          r.districtId(), r.roofCellId(), FacilityType.GREEN_ROOF, BigDecimal.ONE)))
          .isInstanceOf(DomainException.class);
    }
    assertThat(installations.active()).hasSize(1);
    assertThat(installations.active().getFirst().id()).isEqualTo(installed.id());
    assertThatThrownBy(() -> service.save(owner.username(), r))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.SITE_OCCUPIED));
    assertThatThrownBy(() -> service.save(foreign.username(), mode(r, "OTHER")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.PLACEMENT_INVALID));
    assertThat(validator.validate(mode(r, "OTHER"))).isNotEmpty();
  }

  HttpResponse<String> http(HttpClient client, String method, String path, Object body, String csrf)
      throws Exception {
    var builder =
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
            .timeout(Duration.ofSeconds(30));
    if (csrf != null) builder.header("X-CSRF-TOKEN", csrf);
    if (body != null) builder.header("Content-Type", "application/json");
    return client.send(
        builder
            .method(
                method,
                body == null
                    ? HttpRequest.BodyPublishers.noBody()
                    : HttpRequest.BodyPublishers.ofString(json.write(body)))
            .build(),
        HttpResponse.BodyHandlers.ofString());
  }

  HttpClient login(Account account) throws Exception {
    var password = UUID.randomUUID() + "Aa9!";
    db.update(
        "UPDATE accounts SET password_hash=? WHERE id=?", passwords.encode(password), account.id());
    var client =
        HttpClient.newBuilder()
            .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
            .build();
    var csrf =
        json.tree(http(client, "GET", "/auth/csrf", null, null).body()).path("token").asString();
    assertThat(
            http(
                    client,
                    "POST",
                    "/auth/login",
                    Map.of("username", account.username(), "password", password),
                    csrf)
                .statusCode())
        .isEqualTo(200);
    return client;
  }

  @Test
  void historicalHttpRequestReadbackKeepsCsrfOwnershipAndWeeklyRestrictions() throws Exception {
    var foreign = account("11710");
    var owner = login(foreign);
    var r = request();
    var csrf =
        json.tree(http(owner, "GET", "/auth/csrf", null, null).body()).path("token").asString();
    String path = "/installations/cistern-plans";
    assertThat(http(HttpClient.newHttpClient(), "GET", path, null, null).statusCode())
        .isEqualTo(401);
    assertThat(http(owner, "POST", path, mode(r, "HISTORICAL"), null).statusCode()).isEqualTo(403);
    assertThat(http(owner, "POST", path, r, csrf).statusCode()).isEqualTo(403);
    assertThat(http(owner, "POST", path, mode(r, "OTHER"), csrf).statusCode()).isEqualTo(400);
    var response = http(owner, "POST", path, mode(r, "HISTORICAL"), csrf);
    assertThat(response.statusCode()).isEqualTo(200);
    var plan = json.tree(response.body());
    assertThat(plan.path("snapshot").path("request").path("mode").asString())
        .isEqualTo("HISTORICAL");
    var loaded = http(owner, "GET", path, null, null);
    assertThat(json.tree(loaded.body()).get(0)).isEqualTo(plan);
    var again = http(owner, "POST", path, mode(r, "HISTORICAL"), csrf);
    assertThat(json.tree(again.body()).path("id")).isEqualTo(plan.path("id"));
    var other = login(account("11710"));
    var otherCsrf =
        json.tree(http(other, "GET", "/auth/csrf", null, null).body()).path("token").asString();
    assertThat(json.tree(http(other, "GET", path, null, null).body()).isEmpty()).isTrue();
    assertThat(
            http(other, "DELETE", path + "/" + plan.path("id").asString(), null, otherCsrf)
                .statusCode())
        .isEqualTo(404);
    String output = System.getProperty("waterleague.integration.cistern.fixture");
    if (output != null)
      Files.writeString(Path.of(output), response.body(), StandardOpenOption.CREATE_NEW);
    db.update("UPDATE accounts SET approval_status='SUSPENDED' WHERE id=?", foreign.id());
    assertThat(http(owner, "POST", path, mode(r, "HISTORICAL"), csrf).statusCode()).isEqualTo(403);
    assertThat(installations.active()).isEmpty();
  }

  @Test
  void immutableSourceCostsIdempotencyAndNoSpending() {
    var owner = account("11200");
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
    var owner = account("11200");
    var other = account("11200");
    var foreign = account("11710");
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
    var owner = account("11200");
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
                r.districtId(),
                r.groundCellId(),
                FacilityType.valueOf(ground.allowedTypes().getFirst()),
                BigDecimal.ONE));
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
    var owner = account("11200");
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

  @Autowired io.waterleague.facility.repository.CisternSpecificationRepository specifications;

  CisternPlanRequest equipmentRequest(String id, String hash, BigDecimal offset) {
    var r = request();
    return new CisternPlanRequest(
        r.districtId(),
        r.roofCellId(),
        r.groundCellId(),
        r.roofModelHash(),
        r.groundModelHash(),
        r.captureAreaM2(),
        null,
        null,
        null,
        new CisternEquipmentRequest(id, hash, offset, BigDecimal.ZERO, BigDecimal.ZERO));
  }

  @Test
  void publicEquipmentRetainsSourceNominalCapacityAndNoSpending() {
    var owner = account("11200");
    var before = budget.view(owner.id()).remainingKrw();
    var r =
        equipmentRequest(
            "SINYOUNG_STS_1500L_2025",
            io.waterleague.facility.repository.CisternSpecificationRepository.HASH,
            BigDecimal.ZERO);
    assertThat(validator.validate(r)).isEmpty();
    var first = service.save(owner.username(), r);
    var s = first.snapshot();
    assertThat(s.path("schemaVersion").asInt()).isEqualTo(3);
    assertThat(s.path("capacityM3").decimalValue()).isEqualByComparingTo("1.5");
    var g = s.path("equipmentGeometry");
    assertThat(g.path("widthM").asDouble()).isEqualTo(0.8);
    assertThat(g.path("lengthM").asDouble()).isEqualTo(1.8);
    assertThat(g.path("heightM").asDouble()).isEqualTo(1.45);
    assertThat(g.path("sourceModelHash").asString()).isEqualTo(ground.modelHash());
    assertThat(s.path("equipmentSpecification"))
        .isEqualTo(
            specifications.require(r.equipment().specificationId(), r.equipment().catalogSha256()));
    assertThat(s.path("equipmentSpecification").path("hydraulics").path("internalAreaM2").isNull())
        .isTrue();
    assertThat(
            s.path("equipmentSpecification")
                .path("procurement")
                .path("confirmedInstallationPriceKrw")
                .isNull())
        .isTrue();
    assertThat(s.path("tankGeometry").isMissingNode()).isTrue();
    assertThat(s.path("request").path("tankAreaM2").isNull()).isTrue();
    assertThat(s.path("installationReady").asBoolean()).isFalse();
    assertThat(s.path("positionReserved").asBoolean()).isFalse();
    assertThat(service.save(owner.username(), r).id()).isEqualTo(first.id());
    assertThat(service.list(owner.username()).getFirst().snapshot()).isEqualTo(s);
    assertThat(installations.active()).isEmpty();
    assertThat(budget.view(owner.id()).remainingKrw()).isEqualByComparingTo(before);
    var hybrid =
        new CisternPlanRequest(
            r.districtId(),
            r.roofCellId(),
            r.groundCellId(),
            r.roofModelHash(),
            r.groundModelHash(),
            r.captureAreaM2(),
            BigDecimal.ONE,
            BigDecimal.ONE,
            null,
            r.equipment());
    assertThat(validator.validate(hybrid)).isNotEmpty();
    assertThatThrownBy(() -> service.save(owner.username(), hybrid))
        .isInstanceOf(DomainException.class);
    for (var invalid :
        List.of(
            equipmentRequest("UNKNOWN", r.equipment().catalogSha256(), BigDecimal.ZERO),
            equipmentRequest(r.equipment().specificationId(), "0".repeat(64), BigDecimal.ZERO),
            equipmentRequest(
                r.equipment().specificationId(),
                r.equipment().catalogSha256(),
                new BigDecimal("10000")))) {
      assertThatThrownBy(() -> service.save(owner.username(), invalid))
          .isInstanceOf(DomainException.class);
    }
    assertThat(service.list(owner.username())).hasSize(1);
    db.update(
        "UPDATE cistern_map_plans SET snapshot_text=replace(snapshot_text, '1.45', '1.46') WHERE"
            + " id=?",
        first.id());
    assertThatThrownBy(() -> service.list(owner.username())).isInstanceOf(DomainException.class);
  }

  @Test
  void concurrentRetryCreatesOneDraft() throws Exception {
    var owner = account("11200");
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
