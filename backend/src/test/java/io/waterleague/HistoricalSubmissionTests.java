package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.historical.dto.HistoricalSubmissionRequest;
import io.waterleague.historical.service.*;
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
class HistoricalSubmissionTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(org.springframework.test.context.DynamicPropertyRegistry r) {
    SharedInstallationTests.integrationDatabase(r);
  }

  @Autowired HistoricalSubmissionService service;
  @Autowired HistoricalService history;
  @Autowired HistoricalDesignService designService;
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
    db.update("DELETE FROM historical_experiments");
    owner = UUID.randomUUID();
    accounts.add(
        new Account(
            owner,
            "submit_" + owner.toString().substring(0, 8),
            "재해 제출 시험",
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

  HistoricalSubmissionRequest.Item item(String district, String area, int second) {
    var site =
        NativeSiteFixtures.sites(sites, district).values().stream()
            .filter(
                s ->
                    s.existingInfrastructure() == null
                        && s.allowedTypes().contains("GREEN_ROOF")
                        && s.maxAreaM2().compareTo(new BigDecimal(area)) >= 0)
            .findFirst()
            .orElseThrow();
    return new HistoricalSubmissionRequest.Item(
        district,
        site.cellId(),
        FacilityType.GREEN_ROOF,
        new BigDecimal(area),
        start.plusSeconds(second),
        null);
  }

  HistoricalSubmissionRequest request(List<HistoricalSubmissionRequest.Item> rows) {
    return new HistoricalSubmissionRequest(UUID.randomUUID(), eventId, rows);
  }

  io.waterleague.historical.dto.HistoricalDesignRequest.Item designItem(
      String district, int second) {
    var p = item(district, "20", second);
    return new io.waterleague.historical.dto.HistoricalDesignRequest.Item(
        UUID.randomUUID(),
        p.districtId(),
        p.cellId(),
        p.facilityType(),
        p.areaM2(),
        p.installedAt());
  }

  io.waterleague.historical.dto.HistoricalDesignSubmissionRequest reference(
      io.waterleague.historical.view.HistoricalDesignView saved) {
    return new io.waterleague.historical.dto.HistoricalDesignSubmissionRequest(
        UUID.randomUUID(), saved.revision(), saved.snapshotSha256());
  }

  Map<String, Object> nativeRequest(UUID id) {
    var job = history.require(owner, id);
    return Map.of(
        "modelHash", job.modelHash(), "inputHash", job.inputHash(), "placements", job.placements());
  }

  @Test
  void savedDesignSubmissionPreservesCostsAndSurvivesLaterCancellation() throws Exception {
    var first = designItem("11200", 137);
    var second = designItem("11680", 3717);
    var design =
        designService.save(
            owner,
            eventId,
            new io.waterleague.historical.dto.HistoricalDesignRequest(
                UUID.randomUUID(), 0, 3717, List.of(first, second)));
    var ref = reference(design);
    var submitted = service.submitSaved(owner, eventId, ref);
    assertThat(submitted.designRevision()).isEqualTo(1L);
    var original = nativeRequest(submitted.id());
    var rows = json.tree(original.get("placements").toString());
    assertThat(json.tree(rows.get(0).path("submissionDesignSnapshotRaw").asString()))
        .isEqualTo(design.snapshot());
    assertThat(rows.get(0).path("submissionDesignSnapshotSha256").asString())
        .isEqualTo(design.snapshotSha256());
    for (var row : rows) {
      assertThat(row.has("installedAt")).isFalse();
      var savedRow =
          java.util.stream.StreamSupport.stream(
                  design.snapshot().path("placements").spliterator(), false)
              .filter(
                  p ->
                      p.path("item")
                          .path("districtId")
                          .asString()
                          .equals(row.path("districtId").asString()))
              .findFirst()
              .orElseThrow();
      assertThat(row.path("costSnapshotRaw")).isEqualTo(savedRow.path("costSnapshotRaw"));
      assertThat(row.path("experimentInstalledAt"))
          .isEqualTo(savedRow.path("item").path("installedAt"));
    }
    var cancelled =
        designService.save(
            owner,
            eventId,
            new io.waterleague.historical.dto.HistoricalDesignRequest(
                UUID.randomUUID(), 1, 5000, List.of(first)));
    assertThatThrownBy(() -> service.submitSaved(owner, eventId, reference(design)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_CONFLICT));
    assertThat(service.submitSaved(owner, eventId, ref).id()).isEqualTo(submitted.id());
    var next = service.submitSaved(owner, eventId, reference(cancelled));
    assertThat(next.placementCount()).isEqualTo(1);
    assertThat(nativeRequest(submitted.id())).isEqualTo(original);
    var export = System.getProperty("waterleague.integration.submission.design.fixture");
    if (export != null)
      java.nio.file.Files.writeString(
          java.nio.file.Path.of(export),
          json.write(
              Map.of(
                  "design",
                  design,
                  "cancelledDesign",
                  cancelled,
                  "original",
                  original,
                  "cancelled",
                  nativeRequest(next.id()))),
          java.nio.file.StandardOpenOption.CREATE_NEW);
  }

  @Test
  void savedDesignConcurrentSubmitIsIdempotentAndRejectsForeignOrAlteredReference()
      throws Exception {
    var design =
        designService.save(
            owner,
            eventId,
            new io.waterleague.historical.dto.HistoricalDesignRequest(
                UUID.randomUUID(), 0, 137, List.of(designItem("11200", 137))));
    var ref = reference(design);
    try (var executor = Executors.newFixedThreadPool(2)) {
      var gate = new CountDownLatch(1);
      Callable<UUID> call =
          () -> {
            gate.await();
            return service.submitSaved(owner, eventId, ref).id();
          };
      var a = executor.submit(call);
      var b = executor.submit(call);
      gate.countDown();
      assertThat(a.get(30, TimeUnit.SECONDS)).isEqualTo(b.get(30, TimeUnit.SECONDS));
    }
    assertThat(service.list(owner, eventId)).hasSize(1);
    UUID foreign = UUID.randomUUID();
    accounts.add(
        new Account(
            foreign,
            "foreign_" + foreign.toString().substring(0, 8),
            "다른 시험 회원",
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
    assertThatThrownBy(() -> service.submitSaved(foreign, eventId, ref))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.submitSaved(
                    owner,
                    eventId,
                    new io.waterleague.historical.dto.HistoricalDesignSubmissionRequest(
                        UUID.randomUUID(), 1, "0".repeat(64))))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_CONFLICT));
    assertThatThrownBy(
            () ->
                service.submit(
                    owner,
                    new HistoricalSubmissionRequest(
                        ref.requestKey(), eventId, List.of(item("11200", "20", 137)))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
  }

  @Test
  void savedDesignHashOrPriceCorruptionDoesNotCreateAJob() {
    var design =
        designService.save(
            owner,
            eventId,
            new io.waterleague.historical.dto.HistoricalDesignRequest(
                UUID.randomUUID(), 0, 137, List.of(designItem("11200", 137))));
    db.update(
        "UPDATE historical_design_revisions SET snapshot_raw=? WHERE owner_id=?", "{}", owner);
    assertThatThrownBy(() -> service.submitSaved(owner, eventId, reference(design)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_DESIGN_INVALID));
    var changed = (tools.jackson.databind.node.ObjectNode) json.tree(json.write(design.snapshot()));
    ((tools.jackson.databind.node.ObjectNode) changed.path("placements").get(0)).put("cost", 1);
    String raw = json.write(changed), hash = json.hash(raw);
    db.update(
        "UPDATE historical_design_revisions SET snapshot_raw=?,snapshot_sha256=? WHERE owner_id=?",
        raw,
        hash,
        owner);
    assertThatThrownBy(
            () ->
                service.submitSaved(
                    owner,
                    eventId,
                    new io.waterleague.historical.dto.HistoricalDesignSubmissionRequest(
                        UUID.randomUUID(), 1, hash)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_SITE_CHANGED));
    assertThat(service.list(owner, eventId)).isEmpty();
  }

  @Test
  void freezesAllDistrictsAndRetriesOneJobConcurrently() throws Exception {
    var dto = request(List.of(item("11200", "20", 137), item("11680", "20", 197)));
    try (var executor = Executors.newFixedThreadPool(2)) {
      var gate = new CountDownLatch(1);
      Callable<UUID> call =
          () -> {
            gate.await();
            return service.submit(owner, dto).id();
          };
      var a = executor.submit(call);
      var b = executor.submit(call);
      gate.countDown();
      assertThat(a.get(30, TimeUnit.SECONDS)).isEqualTo(b.get(30, TimeUnit.SECONDS));
    }
    var job = service.list(owner, eventId).getFirst();
    assertThat(service.list(owner, eventId)).hasSize(1);
    var frozen = history.require(owner, job.id());
    var export = System.getProperty("waterleague.integration.historical.request");
    if (export != null)
      java.nio.file.Files.writeString(
          java.nio.file.Path.of(export),
          json.write(
              Map.of(
                  "modelHash",
                  frozen.modelHash(),
                  "inputHash",
                  frozen.inputHash(),
                  "placements",
                  frozen.placements())),
          java.nio.file.StandardOpenOption.CREATE_NEW);
    assertThat(frozen.inputHash())
        .isEqualTo(json.hash(frozen.modelHash() + "\n" + frozen.placements()));
    assertThat(frozen.placements())
        .contains(
            "FULL_EVENT_INDEPENDENT_SURFACES_V1",
            "experimentInstalledAt",
            "11200",
            "11680",
            "costSnapshotRaw",
            "budgetAccounting",
            "submissionRequestRaw");
    assertThat(frozen.placements()).doesNotContain("\"installedAt\":\"2022");
    assertThat(service.list(UUID.randomUUID(), eventId)).isEmpty();
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
    assertThatThrownBy(
            () ->
                service.submit(
                    owner,
                    new HistoricalSubmissionRequest(
                        dto.requestKey(), eventId, List.of(dto.placements().getFirst()))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThat(history.require(owner, job.id()).placements()).isEqualTo(frozen.placements());
  }

  @Test
  void rejectsCrossDistrictBudgetDuplicateAndForeignParentAtomically() {
    assertThatThrownBy(
            () ->
                service.submit(
                    owner, request(List.of(item("11200", "3000", 20), item("11680", "3000", 40)))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
    var p = item("11200", "20", 137);
    assertThatThrownBy(() -> service.submit(owner, request(List.of(p, p))))
        .isInstanceOf(DomainException.class);
    var invalid =
        new HistoricalSubmissionRequest.Item(
            p.districtId(),
            p.cellId(),
            p.facilityType(),
            p.areaM2(),
            p.installedAt(),
            UUID.randomUUID());
    assertThatThrownBy(() -> service.submit(owner, request(List.of(invalid))))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    assertThat(service.list(owner, eventId)).isEmpty();
    assertThat(history.list(owner)).isEmpty();
  }

  @Test
  void boardSeparatesRulesKeepsNegativeAndExcludesFailuresAndUnapprovedMembers() {
    var dto = request(List.of(item("11200", "20", 10)));
    var a = service.submit(owner, dto);
    var p = dto.placements().getFirst();
    assertThatThrownBy(
            () ->
                history.create(
                    owner,
                    new io.waterleague.historical.dto.HistoricalRequest(
                        dto.requestKey(),
                        p.districtId(),
                        history.require(owner, a.id()).modelHash(),
                        List.of(
                            new io.waterleague.historical.dto.HistoricalRequest.Item(
                                p.cellId(), p.facilityType(), p.areaM2())))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    db.update("UPDATE historical_experiments SET state='SUCCEEDED',result='{}' WHERE id=?", a.id());
    db.update("UPDATE historical_submissions SET difference_m3=-0.25 WHERE job_id=?", a.id());
    var b = service.submit(owner, request(List.of(item("11200", "20", 20))));
    db.update("UPDATE historical_experiments SET state='SUCCEEDED',result='{}' WHERE id=?", b.id());
    db.update("UPDATE historical_submissions SET difference_m3=-0.5 WHERE job_id=?", b.id());
    var board = json.tree(json.write(service.board(eventId)));
    assertThat(board.path("groups").size()).isEqualTo(1);
    assertThat(board.path("groups").get(0).path("entries").size()).isEqualTo(1);
    assertThat(board.path("groups").get(0).path("entries").get(0).path("differenceM3").asDouble())
        .isEqualTo(-.25);
    db.update(
        "UPDATE historical_submissions SET rules_hash=? WHERE job_id=?", "a".repeat(64), b.id());
    assertThat(json.tree(json.write(service.board(eventId))).path("groups").size()).isEqualTo(2);
    db.update("UPDATE historical_experiments SET state='FAILED' WHERE id=?", b.id());
    assertThat(json.tree(json.write(service.board(eventId))).path("groups").size()).isEqualTo(1);
    db.update("UPDATE accounts SET enabled=false WHERE id=?", owner);
    assertThat(json.tree(json.write(service.board(eventId))).path("groups").size()).isZero();
  }

  @Test
  void preservesNestedSubmissionBundleAndRejectsTampering(
      @org.junit.jupiter.api.io.TempDir java.nio.file.Path root) throws Exception {
    root = root.toRealPath();
    UUID id = UUID.randomUUID(), lease = UUID.randomUUID();
    var directory = root.resolve("historical").resolve(id.toString()).resolve(lease.toString());
    String rules = "{\"policy\":\"FULL_EVENT_INDEPENDENT_SURFACES_V1\"}";
    String placements =
        json.write(
            List.of(
                Map.of(
                    "submissionPolicy",
                    HistoricalSubmissionService.POLICY,
                    "submissionRulesHash",
                    json.hash(rules))));
    String model = "a".repeat(64),
        hash = json.hash(model + "\n" + placements),
        result = "{\"testOnly\":true}";
    var files =
        new TreeMap<>(
            Map.of(
                "request.json",
                json.write(Map.of("modelHash", model, "inputHash", hash, "placements", placements)),
                "result.json",
                result,
                "submission.py",
                "# 제출 시험\n",
                "historical.py",
                "# 구별 시험\n",
                "submission-rules.json",
                rules,
                "submission-request.json",
                "{}",
                "11680/0/strategy.inp",
                "PUBLIC_TEST_INPUT"));
    var hashes = new TreeMap<String, String>();
    for (var f : files.entrySet()) {
      java.nio.file.Files.createDirectories(directory.resolve(f.getKey()).getParent());
      java.nio.file.Files.writeString(directory.resolve(f.getKey()), f.getValue());
      hashes.put(f.getKey(), json.hash(f.getValue()));
    }
    java.nio.file.Files.writeString(directory.resolve("manifest.json"), json.write(hashes));
    var job =
        new io.waterleague.historical.entity.HistoricalExperiment(
            id,
            owner,
            "11680",
            model,
            hash,
            placements,
            "SUCCEEDED",
            lease,
            Instant.now(),
            result,
            null);
    var artifacts = new HistoricalArtifactService(root.toString(), json);
    assertThat(artifacts.bundle(job)).isNotEmpty();
    java.nio.file.Files.writeString(directory.resolve("11680/0/strategy.inp"), "CHANGED");
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
    java.nio.file.Files.writeString(
        directory.resolve("11680/0/strategy.inp"), files.get("11680/0/strategy.inp"));
    java.nio.file.Files.delete(directory.resolve("11680/0/strategy.inp"));
    var outside = root.resolve("outside.inp");
    java.nio.file.Files.writeString(outside, "PUBLIC_TEST_INPUT");
    java.nio.file.Files.createSymbolicLink(directory.resolve("11680/0/strategy.inp"), outside);
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
  }
}
