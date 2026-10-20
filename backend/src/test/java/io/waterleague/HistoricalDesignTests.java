package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.historical.dto.HistoricalDesignRequest;
import io.waterleague.historical.repository.HistoricalDesignRepository;
import io.waterleague.historical.service.HistoricalDesignService;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class HistoricalDesignTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry r) {
    SharedInstallationTests.integrationDatabase(r);
  }

  @Autowired HistoricalDesignService service;
  @Autowired io.waterleague.historical.service.HistoricalService history;
  @Autowired SiteCatalogRepository sites;
  @Autowired AccountRepository accounts;
  @Autowired io.waterleague.disaster.service.DisasterService disasters;
  @Autowired JdbcTemplate db;
  @Autowired JsonService json;
  UUID owner;
  String eventId;
  Instant start;

  @BeforeEach
  void prepare() {
    owner = UUID.randomUUID();
    accounts.add(
        new Account(
            owner,
            "draft_" + owner.toString().substring(0, 8),
            "설계 복원 시험",
            "NOT_A_LOGIN",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            "11680",
            "AFFILIATED"));
    var event = disasters.catalog().events().getFirst();
    eventId = event.id();
    start = Instant.parse(event.regions().getFirst().start());
  }

  HistoricalDesignRequest.Item item(String district, String area, int second) {
    var site =
        NativeSiteFixtures.sites(sites, district).values().stream()
            .filter(
                s ->
                    s.existingInfrastructure() == null
                        && s.allowedTypes().contains("GREEN_ROOF")
                        && s.maxAreaM2().compareTo(new BigDecimal(area)) >= 0)
            .findFirst()
            .orElseThrow();
    return new HistoricalDesignRequest.Item(
        UUID.randomUUID(),
        district,
        site.cellId(),
        FacilityType.GREEN_ROOF,
        new BigDecimal(area),
        start.plusSeconds(second));
  }

  HistoricalDesignRequest request(long revision, List<HistoricalDesignRequest.Item> rows) {
    return new HistoricalDesignRequest(UUID.randomUUID(), revision, 400, rows);
  }

  long count() {
    return db.queryForObject(
        "SELECT count(*) FROM historical_design_revisions WHERE owner_id=?", Long.class, owner);
  }

  @Test
  void multiDistrictDesignAndLastCancellationSurviveRepositoryReconnect() throws Exception {
    var first =
        service.save(
            owner,
            eventId,
            request(0, List.of(item("11200", "20", 137), item("11680", "20", 197))));
    assertThat(first.revision()).isEqualTo(1);
    assertThat(first.snapshot().path("placements").size()).isEqualTo(2);
    var again = new HistoricalDesignRepository(db).latest(owner, eventId).orElseThrow();
    assertThat(first.snapshotSha256()).isEqualTo(json.hash(again.snapshotRaw()));
    var export = System.getProperty("waterleague.integration.design.fixture");
    if (export != null)
      java.nio.file.Files.writeString(
          java.nio.file.Path.of(export),
          json.write(first),
          java.nio.file.StandardOpenOption.CREATE_NEW);
    assertThat(again.snapshotSha256()).isEqualTo(first.snapshotSha256());
    var empty = service.save(owner, eventId, request(1, List.of()));
    assertThat(empty.revision()).isEqualTo(2);
    assertThat(service.get(owner, eventId).snapshot().path("placements").size()).isZero();
    assertThat(service.revision(owner, eventId, 1).snapshot()).isEqualTo(first.snapshot());
    assertThat(first.snapshot().toString())
        .contains("costSnapshotRaw", "installedAt", start.plusSeconds(137).toString(), "site");
    assertThat(count()).isEqualTo(2);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM historical_experiments WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void simultaneousDifferentEditsAcceptOneRevisionAndRetryIsIdempotent() throws Exception {
    var a = request(0, List.of(item("11200", "20", 137)));
    var b = request(0, List.of(item("11680", "20", 197)));
    var gate = new CountDownLatch(1);
    try (var threads = Executors.newFixedThreadPool(2)) {
      var outcomes = new ArrayList<Future<String>>();
      for (var dto : List.of(a, b))
        outcomes.add(
            threads.submit(
                () -> {
                  gate.await();
                  try {
                    service.save(owner, eventId, dto);
                    return dto.requestKey().toString();
                  } catch (DomainException e) {
                    return e.code().name();
                  }
                }));
      gate.countDown();
      var values =
          List.of(
              outcomes.get(0).get(30, TimeUnit.SECONDS), outcomes.get(1).get(30, TimeUnit.SECONDS));
      assertThat(values).contains("HISTORICAL_DESIGN_CONFLICT");
      var winner = values.contains(a.requestKey().toString()) ? a : b;
      assertThat(service.save(owner, eventId, winner).revision()).isEqualTo(1);
      assertThat(count()).isEqualTo(1);
      assertThatThrownBy(
              () ->
                  service.save(
                      owner,
                      eventId,
                      new HistoricalDesignRequest(
                          winner.requestKey(), 0, 401, winner.placements())))
          .isInstanceOfSatisfying(
              DomainException.class,
              e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_CONFLICT));
    }
  }

  @Test
  void locationTimeBudgetAndPublicOccupancyFailuresDoNotAppend() {
    var p = item("11200", "20", 137);
    assertThatThrownBy(() -> service.save(owner, eventId, request(0, List.of(p, p))))
        .isInstanceOf(DomainException.class);
    var future =
        new HistoricalDesignRequest.Item(
            p.id(),
            p.districtId(),
            p.cellId(),
            p.facilityType(),
            p.areaM2(),
            start.minusSeconds(1));
    assertThatThrownBy(() -> service.save(owner, eventId, request(0, List.of(future))))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.save(
                    owner,
                    eventId,
                    request(0, List.of(item("11200", "3000", 20), item("11680", "3000", 40)))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
    var invalid =
        new HistoricalDesignRequest.Item(
            UUID.randomUUID(),
            p.districtId(),
            "RW653831038",
            p.facilityType(),
            BigDecimal.ONE,
            start);
    assertThatThrownBy(() -> service.save(owner, eventId, request(0, List.of(invalid))))
        .isInstanceOf(DomainException.class);
    assertThat(count()).isZero();
  }

  @Test
  void ownershipEventAndImmutableFacilityIdentityRemainSeparate() {
    var p = item("11200", "20", 137);
    var first = service.save(owner, eventId, request(0, List.of(p)));
    assertThat(service.get(UUID.randomUUID(), eventId).revision()).isZero();
    assertThatThrownBy(() -> service.revision(UUID.randomUUID(), eventId, 1))
        .isInstanceOf(DomainException.class);
    var another =
        disasters.catalog().events().stream()
            .filter(e -> !e.id().equals(eventId))
            .findFirst()
            .orElseThrow();
    assertThat(service.get(owner, another.id()).revision()).isZero();
    var changed =
        new HistoricalDesignRequest.Item(
            p.id(),
            p.districtId(),
            p.cellId(),
            p.facilityType(),
            p.areaM2(),
            start.plusSeconds(200));
    assertThatThrownBy(() -> service.save(owner, eventId, request(1, List.of(changed))))
        .isInstanceOf(DomainException.class);
    var second = service.save(owner, eventId, request(1, List.of(p, item("11680", "20", 197))));
    assertThat(second.snapshot().path("placements"))
        .contains(first.snapshot().path("placements").get(0));
    assertThat(service.revision(owner, eventId, 1).snapshotSha256())
        .isEqualTo(first.snapshotSha256());
  }

  @Test
  void storedSnapshotTamperingFailsClosed() {
    service.save(owner, eventId, request(0, List.of(item("11200", "20", 137))));
    db.update("UPDATE historical_design_revisions SET snapshot_raw='{}' WHERE owner_id=?", owner);
    assertThatThrownBy(() -> service.get(owner, eventId))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_INVALID));
  }

  io.waterleague.historical.dto.HistoricalRequest calculation(
      UUID key, long revision, List<HistoricalDesignRequest.Item> items) {
    String district = items.getFirst().districtId();
    String model =
        disasters.catalog().events().stream()
            .filter(e -> e.id().equals(eventId))
            .findFirst()
            .orElseThrow()
            .regions()
            .stream()
            .filter(r -> r.districtId().equals(district))
            .findFirst()
            .orElseThrow()
            .modelHash();
    return new io.waterleague.historical.dto.HistoricalRequest(
        key,
        district,
        model,
        items.stream()
            .map(
                p ->
                    new io.waterleague.historical.dto.HistoricalRequest.Item(
                        p.cellId(),
                        p.facilityType(),
                        p.areaM2(),
                        p.installedAt(),
                        sites.require(district, p.cellId()).modelHash()))
            .toList(),
        null,
        "INSTALLATION_TIME_EXPERIMENT_V1",
        null,
        revision,
        eventId);
  }

  @Test
  void allDistrictCalculationsBindOneSavedDesignAndPreserveItsCostSource() throws Exception {
    var items = new ArrayList<HistoricalDesignRequest.Item>();
    for (String district : List.of("11680", "11200")) {
      var site =
          NativeSiteFixtures.sites(sites, district).values().stream()
              .filter(
                  v ->
                      v.kind().equals("ROOF")
                          && v.existingInfrastructure() == null
                          && v.maxAreaM2().compareTo(new BigDecimal("20")) >= 0)
              .sorted(Comparator.comparing(io.waterleague.installation.view.SiteView::cellId))
              .findFirst()
              .orElseThrow();
      items.add(
          new HistoricalDesignRequest.Item(
              UUID.randomUUID(),
              district,
              site.cellId(),
              FacilityType.GREEN_ROOF,
              new BigDecimal("20"),
              start.plusSeconds(items.isEmpty() ? 137 : 3717)));
    }
    var saved = service.save(owner, eventId, request(0, items));
    var exported = new ArrayList<Object>();
    for (var p : items) {
      var dto = calculation(UUID.randomUUID(), 1, List.of(p));
      var job = history.create(owner, dto);
      var row = job.placements().get(0);
      assertThat(row.path("designSnapshotSha256").asString()).isEqualTo(saved.snapshotSha256());
      assertThat(json.hash(row.path("designSnapshotRaw").asString()))
          .isEqualTo(saved.snapshotSha256());
      assertThat(
              row.path("wholeDesignBudgetAccounting")
                  .path("programs")
                  .get(0)
                  .path("allocatedKrw")
                  .decimalValue())
          .isEqualByComparingTo("14000000");
      var source =
          saved
              .snapshot()
              .path("placements")
              .valueStream()
              .filter(v -> v.path("item").path("districtId").asString().equals(p.districtId()))
              .findFirst()
              .orElseThrow();
      assertThat(row.path("costSnapshotRaw")).isEqualTo(source.path("costSnapshotRaw"));
      assertThat(history.create(owner, dto).id()).isEqualTo(job.id());
      var original = history.require(owner, job.id());
      exported.add(
          Map.of(
              "modelHash",
              original.modelHash(),
              "placements",
              original.placements(),
              "inputHash",
              original.inputHash()));
    }
    String target = System.getProperty("waterleague.integration.design.run.fixture");
    if (target != null)
      java.nio.file.Files.writeString(
          java.nio.file.Path.of(target),
          json.write(Map.of("design", saved, "requests", exported)),
          java.nio.file.StandardOpenOption.CREATE_NEW);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM historical_experiments WHERE owner_id=?",
                Integer.class,
                owner))
        .isEqualTo(2);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void staleForeignAndAlteredSavedDesignCalculationsAreRejectedAtomically() {
    var p = item("11200", "20", 137);
    service.save(owner, eventId, request(0, List.of(p)));
    var dto = calculation(UUID.randomUUID(), 1, List.of(p));
    assertThatThrownBy(() -> history.create(UUID.randomUUID(), dto))
        .isInstanceOf(DomainException.class);
    var changed =
        new HistoricalDesignRequest.Item(
            p.id(),
            p.districtId(),
            p.cellId(),
            p.facilityType(),
            new BigDecimal("10"),
            p.installedAt());
    assertThatThrownBy(
            () -> history.create(owner, calculation(UUID.randomUUID(), 1, List.of(changed))))
        .isInstanceOf(DomainException.class);
    var job = history.create(owner, dto);
    service.save(owner, eventId, request(1, List.of()));
    assertThat(history.create(owner, dto).id()).isEqualTo(job.id());
    assertThatThrownBy(() -> history.create(owner, calculation(UUID.randomUUID(), 1, List.of(p))))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_CONFLICT));
    assertThatThrownBy(() -> history.create(owner, calculation(dto.requestKey(), 2, List.of(p))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM historical_experiments WHERE owner_id=?",
                Integer.class,
                owner))
        .isEqualTo(1);
  }

  @Test
  void executionRechecksWholeDesignBudgetEvenWhenSelectedDistrictFits() {
    var a = item("11200", "20", 137);
    var saved = service.save(owner, eventId, request(0, List.of(a, item("11680", "20", 197))));
    var snapshot = saved.snapshot().deepCopy();
    for (var row : snapshot.path("placements"))
      if (!row.path("item").path("districtId").asString().equals(a.districtId()))
        ((tools.jackson.databind.node.ObjectNode) row).put("cost", new BigDecimal("2000000000"));
    // 저장 이후 한도에 맞지 않게 된 과거 설계도 실행 시 전체 사업군 한도로 거부한다.
    String raw = json.write(snapshot);
    db.update(
        "UPDATE historical_design_revisions SET snapshot_raw=?,snapshot_sha256=? WHERE owner_id=?",
        raw,
        json.hash(raw),
        owner);
    assertThatThrownBy(() -> history.create(owner, calculation(UUID.randomUUID(), 1, List.of(a))))
        .isInstanceOf(DomainException.class);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM historical_experiments WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void simultaneousCancellationAndCalculationKeepOneConsistentSnapshot() throws Exception {
    var p = item("11200", "20", 137);
    service.save(owner, eventId, request(0, List.of(p)));
    var dto = calculation(UUID.randomUUID(), 1, List.of(p));
    var gate = new CountDownLatch(1);
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var run =
          pool.submit(
              () -> {
                gate.await();
                try {
                  return history
                      .create(owner, dto)
                      .placements()
                      .get(0)
                      .path("designRevision")
                      .asLong();
                } catch (DomainException e) {
                  assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_CONFLICT);
                  return 0L;
                }
              });
      var cancel =
          pool.submit(
              () -> {
                gate.await();
                return service.save(owner, eventId, request(1, List.of()));
              });
      gate.countDown();
      assertThat(cancel.get(10, TimeUnit.SECONDS).revision()).isEqualTo(2);
      long used = run.get(10, TimeUnit.SECONDS);
      assertThat(used).isIn(0L, 1L);
      assertThat(service.get(owner, eventId).snapshot().path("placements").size()).isZero();
      assertThat(
              db.queryForObject(
                  "SELECT count(*) FROM historical_experiments WHERE owner_id=?",
                  Long.class,
                  owner))
          .isEqualTo(used);
    }
  }
}
