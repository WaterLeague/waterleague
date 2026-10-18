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
class HistoricalDesignTests {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry r) {
    SharedInstallationTests.integrationDatabase(r);
  }

  @Autowired HistoricalDesignService service;
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
            "2410520",
            "AFFILIATED"));
    var event = disasters.catalog().events().getFirst();
    eventId = event.id();
    start = Instant.parse(event.regions().getFirst().start());
  }

  HistoricalDesignRequest.Item item(String district, String area, int second) {
    var site =
        sites.district(district).values().stream()
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
            request(0, List.of(item("2419953", "20", 137), item("2410520", "20", 197))));
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
    var a = request(0, List.of(item("2419953", "20", 137)));
    var b = request(0, List.of(item("2410520", "20", 197)));
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
    var p = item("2419953", "20", 137);
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
                    request(0, List.of(item("2419953", "3000", 20), item("2410520", "3000", 40)))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
    var occupied =
        sites.district("2419953").values().stream()
            .filter(s -> s.existingInfrastructure() != null)
            .findFirst()
            .orElseThrow();
    var invalid =
        new HistoricalDesignRequest.Item(
            UUID.randomUUID(),
            occupied.districtId(),
            occupied.cellId(),
            FacilityType.valueOf(occupied.allowedTypes().getFirst()),
            BigDecimal.ONE,
            start);
    assertThatThrownBy(() -> service.save(owner, eventId, request(0, List.of(invalid))))
        .isInstanceOf(DomainException.class);
    assertThat(count()).isZero();
  }

  @Test
  void ownershipEventAndImmutableFacilityIdentityRemainSeparate() {
    var p = item("2419953", "20", 137);
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
    var second = service.save(owner, eventId, request(1, List.of(p, item("2410520", "20", 197))));
    assertThat(second.snapshot().path("placements"))
        .contains(first.snapshot().path("placements").get(0));
    assertThat(service.revision(owner, eventId, 1).snapshotSha256())
        .isEqualTo(first.snapshotSha256());
  }

  @Test
  void storedSnapshotTamperingFailsClosed() {
    service.save(owner, eventId, request(0, List.of(item("2419953", "20", 137))));
    db.update("UPDATE historical_design_revisions SET snapshot_raw='{}' WHERE owner_id=?", owner);
    assertThatThrownBy(() -> service.get(owner, eventId))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_INVALID));
  }
}
