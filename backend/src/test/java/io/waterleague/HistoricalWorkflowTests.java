package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.historical.dto.HistoricalRequest;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class HistoricalWorkflowTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired AccountRepository accounts;
  @Autowired HistoricalService service;
  @Autowired SiteCatalogRepository sites;
  @Autowired DistrictRepository districts;
  @Autowired io.waterleague.disaster.service.DisasterService disasters;
  @Autowired JdbcTemplate db;
  @Autowired io.waterleague.common.service.JsonService json;
  @Autowired io.waterleague.rainfall.repository.ObservedGameRepository models;
  UUID owner;
  String cell;
  String hash;

  @BeforeEach
  void prepare() {
    db.update("DELETE FROM historical_experiments");
    owner = UUID.randomUUID();
    accounts.add(
        new Account(
            owner,
            "hist_" + owner.toString().substring(0, 8),
            "재해 시험",
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
    hash =
        disasters.catalog().events().getFirst().regions().stream()
            .filter(r -> r.districtId().equals("11200"))
            .findFirst()
            .orElseThrow()
            .modelHash();
    cell =
        NativeSiteFixtures.sites(sites, "11200").keySet().stream()
            .filter(id -> sites.require("11200", id).kind().equals("ROOF"))
            .findFirst()
            .orElseThrow();
  }

  HistoricalRequest request(UUID key, String id, FacilityType type, String amount) {
    return new HistoricalRequest(
        key, "11200", hash, List.of(new HistoricalRequest.Item(id, type, new BigDecimal(amount))));
  }

  HistoricalRequest timed(UUID key, Instant at, UUID parent) {
    return new HistoricalRequest(
        key,
        "11200",
        hash,
        List.of(new HistoricalRequest.Item(cell, FacilityType.GREEN_ROOF, BigDecimal.ONE, at)),
        null,
        "INSTALLATION_TIME_EXPERIMENT_V1",
        parent);
  }

  @Test
  void restoredDesignMustBindItsSavedSiteVersionAndKeepLegacyRetries() {
    var key = UUID.randomUUID();
    var site = sites.require("11200", cell);
    var at =
        Instant.parse(models.require(hash).model().path("rainfall").path("start").asString())
            .plusSeconds(137);
    var wrong =
        new HistoricalRequest(
            key,
            "11200",
            hash,
            List.of(
                new HistoricalRequest.Item(
                    cell, FacilityType.GREEN_ROOF, BigDecimal.ONE, at, "f".repeat(64))),
            null,
            "INSTALLATION_TIME_EXPERIMENT_V1",
            null);
    assertThatThrownBy(() -> service.create(owner, wrong))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.HISTORICAL_SITE_CHANGED));
    assertThat(service.list(owner)).isEmpty();
    var right =
        new HistoricalRequest(
            key,
            "11200",
            hash,
            List.of(
                new HistoricalRequest.Item(
                    cell, FacilityType.GREEN_ROOF, BigDecimal.ONE, at, site.modelHash())),
            null,
            "INSTALLATION_TIME_EXPERIMENT_V1",
            null);
    var saved = service.create(owner, right);
    assertThat(service.create(owner, timed(key, at, null)).id()).isEqualTo(saved.id());
    assertThatThrownBy(() -> service.create(owner, wrong))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
  }

  @Test
  void installationTimeAndParentAreImmutableOwnerBoundInputs() {
    var start =
        Instant.parse(models.require(hash).model().path("rainfall").path("start").asString());
    var firstRequest = timed(UUID.randomUUID(), start.plusSeconds(37), null);
    var first = service.create(owner, firstRequest);
    String original = service.require(owner, first.id()).placements();
    assertThat(first.placements().get(0).path("installedAt").asString())
        .isEqualTo(start.plusSeconds(37).toString());
    assertThat(service.create(owner, firstRequest).id()).isEqualTo(first.id());
    assertThatThrownBy(
            () ->
                service.create(
                    owner, timed(firstRequest.requestKey(), start.plusSeconds(38), null)))
        .isInstanceOf(DomainException.class)
        .extracting("code")
        .isEqualTo(ErrorCode.CONFLICT);
    var secondRequest = timed(UUID.randomUUID(), start.plusSeconds(137), first.id());
    var second = service.create(owner, secondRequest);
    assertThat(second.placements().get(0).path("parentExperimentId").asString())
        .isEqualTo(first.id().toString());
    assertThat(service.create(owner, secondRequest).id()).isEqualTo(second.id());
    assertThat(service.require(owner, first.id()).placements()).isEqualTo(original);
    assertThatThrownBy(
            () ->
                service.create(
                    owner, timed(secondRequest.requestKey(), start.plusSeconds(137), null)))
        .isInstanceOf(DomainException.class)
        .extracting("code")
        .isEqualTo(ErrorCode.CONFLICT);
    assertThatThrownBy(
            () -> service.create(UUID.randomUUID(), timed(UUID.randomUUID(), start, first.id())))
        .isInstanceOf(DomainException.class)
        .extracting("code")
        .isEqualTo(ErrorCode.RESOURCE_NOT_FOUND);
  }

  @Test
  void rejectsOutOfEventAndSubSecondInstallationTimesWithoutWritingJobs() {
    var rain = models.require(hash).model().path("rainfall");
    var start = Instant.parse(rain.path("start").asString());
    var end = Instant.parse(rain.path("end").asString());
    for (var at : List.of(start.minusSeconds(1), start.plusNanos(1), end, end.plusSeconds(1))) {
      assertThatThrownBy(() -> service.create(owner, timed(UUID.randomUUID(), at, null)))
          .isInstanceOf(DomainException.class)
          .extracting("code")
          .isEqualTo(ErrorCode.PLACEMENT_INVALID);
    }
    assertThat(db.queryForObject("SELECT COUNT(*) FROM historical_experiments", Integer.class))
        .isZero();
  }

  @Test
  void swaleUsesSameFixedWidthCapInHistoricalRequests() {
    int before = db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class);
    String district = "11680";
    var site =
        NativeSiteFixtures.sites(sites, district).values().stream()
            .filter(
                c ->
                    c.allowedTypes().contains("VEGETATIVE_SWALE")
                        && c.existingInfrastructure() == null)
            .findFirst()
            .orElseThrow();
    var cap = site.maxAreaFor(FacilityType.VEGETATIVE_SWALE);
    String model =
        disasters.catalog().events().getFirst().regions().stream()
            .filter(r -> r.districtId().equals(district))
            .findFirst()
            .orElseThrow()
            .modelHash();
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        UUID.randomUUID(),
                        district,
                        model,
                        List.of(
                            new HistoricalRequest.Item(
                                site.cellId(),
                                FacilityType.VEGETATIVE_SWALE,
                                cap.add(new BigDecimal("0.01")))))))
        .isInstanceOf(DomainException.class);
    var stateRequest =
        new HistoricalRequest(
            UUID.randomUUID(),
            district,
            model,
            List.of(new HistoricalRequest.Item(site.cellId(), FacilityType.VEGETATIVE_SWALE, cap)),
            site.cellId());
    var job = service.create(owner, stateRequest);
    assertThat(service.require(owner, job.id()).placements())
        .contains(
            "VEGETATIVE_SWALE",
            site.modelHash(),
            "SEOUL_RAINWATER_ACCOUNTING_V4",
            "SELECTED_SWALE_7_DAY_STATE_V2")
        .doesNotContain("SELECTED_SURFACE_7_DAY_DRY_WET_V1");
    assertThat(service.create(owner, stateRequest).id()).isEqualTo(job.id());
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        stateRequest.requestKey(), district, model, stateRequest.placements())))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThat(db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class))
        .isEqualTo(before);
  }

  @Test
  void trenchUsesSameFixedWidthCapInHistoricalRequests() {
    int before = db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class);
    String district = "11680";
    var site =
        NativeSiteFixtures.sites(sites, district).values().stream()
            .filter(
                c ->
                    c.allowedTypes().contains("INFILTRATION_TRENCH")
                        && c.existingInfrastructure() == null)
            .findFirst()
            .orElseThrow();
    var cap = site.maxAreaFor(FacilityType.INFILTRATION_TRENCH);
    String model =
        disasters.catalog().events().getFirst().regions().stream()
            .filter(r -> r.districtId().equals(district))
            .findFirst()
            .orElseThrow()
            .modelHash();
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        UUID.randomUUID(),
                        district,
                        model,
                        List.of(
                            new HistoricalRequest.Item(
                                site.cellId(),
                                FacilityType.INFILTRATION_TRENCH,
                                cap.add(new BigDecimal("0.01")))))))
        .isInstanceOf(DomainException.class);
    var job =
        service.create(
            owner,
            new HistoricalRequest(
                UUID.randomUUID(),
                district,
                model,
                List.of(
                    new HistoricalRequest.Item(
                        site.cellId(), FacilityType.INFILTRATION_TRENCH, cap))));
    assertThat(service.require(owner, job.id()).placements())
        .contains("INFILTRATION_TRENCH", site.modelHash(), "SEOUL_RAINWATER_ACCOUNTING_V4");
    assertThat(db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class))
        .isEqualTo(before);
  }

  @Test
  void pointReferenceRetainsUnknownSiteConditionsAndCurrentRequestIdempotency() throws Exception {
    var site = NativeSiteFixtures.reference(sites);
    String model =
        disasters.catalog().events().getFirst().regions().stream()
            .filter(region -> region.districtId().equals(site.districtId()))
            .findFirst()
            .orElseThrow()
            .modelHash();
    var dto =
        new HistoricalRequest(
            UUID.randomUUID(),
            site.districtId(),
            model,
            List.of(
                new HistoricalRequest.Item(
                    site.cellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE)));
    var job = service.create(owner, dto);
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThat(site.referenceInfrastructure().path("references")).isNotEmpty();
    assertThat(site.siteEligibility()).isEqualTo("UNKNOWN");
    assertThat(service.require(owner, job.id()).placements())
        .contains(site.cellId(), site.modelHash());
  }

  @Test
  void acceptsExpandedSitesAndOtherDistrictsWithoutChangingSharedOccupancy() {
    int before = db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class);
    UUID key = UUID.randomUUID();
    var dto = request(key, cell, FacilityType.GREEN_ROOF, "1.00");
    var job = service.create(owner, dto);
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThat(service.require(owner, job.id()).placements())
        .contains(
            cell,
            "siteModelHash",
            "budgetPolicy",
            "budgetAccounting",
            "publicAssetPolicy",
            "costSnapshotRaw",
            "costSnapshotSha256",
            "SEOUL_RAINWATER_ACCOUNTING_V4",
            "SEOUL_PERSONAL_FULL_2026_V3",
            "2000000000");
    assertThat(service.list(owner)).hasSize(1);
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
    var legacy = json.tree(service.require(owner, job.id()).placements());
    var quote = legacy.get(0).path("costSnapshotRaw").asString();
    assertThat(json.hash(quote)).isEqualTo(legacy.get(0).path("costSnapshotSha256").asString());
    assertThat(json.tree(quote).path("budgetChargeKrw").decimalValue())
        .isEqualByComparingTo("350000");
    ((tools.jackson.databind.node.ObjectNode) legacy.get(0)).remove("costSnapshotRaw");
    ((tools.jackson.databind.node.ObjectNode) legacy.get(0)).remove("costSnapshotSha256");
    ((tools.jackson.databind.node.ObjectNode) legacy.get(0)).remove("budgetAccounting");
    var oldBody = json.write(legacy);
    var oldHash = json.hash(dto.modelHash() + "\n" + oldBody);
    db.update(
        "UPDATE historical_experiments SET placements=?,input_hash=? WHERE id=?",
        oldBody,
        oldHash,
        job.id());
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThat(service.require(owner, job.id()).inputHash()).isEqualTo(oldHash);
    assertThat(db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class))
        .isEqualTo(before);
    assertThatThrownBy(() -> service.require(UUID.randomUUID(), job.id()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    assertThatThrownBy(
            () -> service.create(owner, request(key, cell, FacilityType.GREEN_ROOF, "2.00")))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
  }

  @Test
  void freezesPavementComparisonWithoutChangingDesignAndRejectsConflictingRetries()
      throws Exception {
    var site =
        NativeSiteFixtures.sites(sites, "11200").values().stream()
            .filter(
                s ->
                    s.allowedTypes().contains("PERMEABLE_PAVEMENT")
                        && s.existingInfrastructure() == null
                        && s.maxAreaM2().compareTo(BigDecimal.ONE) >= 0)
            .findFirst()
            .orElseThrow();
    var plain = request(UUID.randomUUID(), site.cellId(), FacilityType.PERMEABLE_PAVEMENT, "1.00");
    var comparison =
        new HistoricalRequest(
            plain.requestKey(),
            "11200",
            hash,
            plain.placements(),
            null,
            null,
            null,
            null,
            null,
            site.cellId());
    var job = service.create(owner, comparison);
    var stored = service.require(owner, job.id());
    assertThat(stored.placements())
        .contains(
            "KWRA_TYPE_A_CLOGGING_REFERENCE_V1",
            io.waterleague.facility.repository.FacilityRepository.PAVEMENT_MAINTENANCE_SHA256);
    assertThat(stored.inputHash()).isEqualTo(json.hash(hash + "\n" + stored.placements()));
    assertThat(service.create(owner, comparison).id()).isEqualTo(job.id());
    assertThatThrownBy(() -> service.create(owner, plain))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    for (var invalid :
        List.of(
            new HistoricalRequest(
                UUID.randomUUID(),
                "11200",
                hash,
                plain.placements(),
                site.cellId(),
                null,
                null,
                null,
                null,
                site.cellId()),
            new HistoricalRequest(
                UUID.randomUUID(),
                "11200",
                hash,
                plain.placements(),
                null,
                null,
                null,
                null,
                null,
                cell))) {
      assertThatThrownBy(() -> service.create(owner, invalid))
          .isInstanceOfSatisfying(
              DomainException.class,
              e -> assertThat(e.code()).isEqualTo(ErrorCode.PLACEMENT_INVALID));
    }
    var roof = request(UUID.randomUUID(), cell, FacilityType.GREEN_ROOF, "1.00");
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        roof.requestKey(),
                        "11200",
                        hash,
                        roof.placements(),
                        null,
                        null,
                        null,
                        null,
                        null,
                        cell)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.PLACEMENT_INVALID));
    var export = System.getProperty("waterleague.integration.pavement.request");
    if (export != null)
      java.nio.file.Files.writeString(
          java.nio.file.Path.of(export),
          json.write(
              Map.of(
                  "districtId",
                  stored.districtId(),
                  "modelHash",
                  stored.modelHash(),
                  "inputHash",
                  stored.inputHash(),
                  "placements",
                  stored.placements())));
  }

  @Test
  void freezesSelectedSensitivityAndRejectsChangedRetriesOrUnplacedTargets() {
    var dto = request(UUID.randomUUID(), cell, FacilityType.GREEN_ROOF, "1.00");
    var selected =
        new HistoricalRequest(
            dto.requestKey(), dto.districtId(), dto.modelHash(), dto.placements(), cell);
    var job = service.create(owner, selected);
    var stored = service.require(owner, job.id());
    assertThat(stored.placements()).contains("SELECTED_SURFACE_7_DAY_DRY_WET_V1");
    assertThat(stored.inputHash()).isEqualTo(json.hash(hash + "\n" + stored.placements()));
    assertThat(service.create(owner, selected).id()).isEqualTo(job.id());
    assertThatThrownBy(() -> service.create(owner, dto))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    var plain = request(UUID.randomUUID(), cell, FacilityType.GREEN_ROOF, "1.00");
    var original = service.create(owner, plain);
    assertThat(service.require(owner, original.id()).placements())
        .doesNotContain("initializationSensitivity");
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        plain.requestKey(), plain.districtId(), hash, plain.placements(), cell)))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        UUID.randomUUID(), dto.districtId(), hash, dto.placements(), "UNPLACED")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.PLACEMENT_INVALID));
    assertThat(service.list(owner)).hasSize(2);
  }

  @Test
  void refusesMismatchedRainfallAndInvalidPlacements() {
    var dto = request(UUID.randomUUID(), cell, FacilityType.GREEN_ROOF, "1.00");
    var wrong =
        new HistoricalRequest(
            dto.requestKey(),
            dto.districtId(),
            districts.require("11680").modelHash(),
            dto.placements());
    assertThatThrownBy(() -> service.create(owner, wrong)).isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.create(
                    owner, request(UUID.randomUUID(), cell, FacilityType.RAIN_GARDEN, "1.00")))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new HistoricalRequest(
                        UUID.randomUUID(),
                        "11200",
                        hash,
                        List.of(dto.placements().getFirst(), dto.placements().getFirst()))))
        .isInstanceOf(DomainException.class);
    var largeRoofs =
        NativeSiteFixtures.sites(sites, "11200").values().stream()
            .filter(
                s ->
                    s.allowedTypes().contains("GREEN_ROOF")
                        && s.maxAreaM2().compareTo(new BigDecimal("3000")) >= 0)
            .limit(2)
            .map(
                s ->
                    request(UUID.randomUUID(), s.cellId(), FacilityType.GREEN_ROOF, "3000")
                        .placements()
                        .getFirst())
            .toList();
    assertThat(largeRoofs).hasSize(2);
    assertThatThrownBy(
            () ->
                service.create(
                    owner, new HistoricalRequest(UUID.randomUUID(), "11200", hash, largeRoofs)))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
    assertThat(service.list(owner)).isEmpty();
  }

  @Test
  void refusesChangedArtifactsAndLinks(@org.junit.jupiter.api.io.TempDir java.nio.file.Path root)
      throws Exception {
    root = root.toRealPath();
    UUID id = UUID.randomUUID(), lease = UUID.randomUUID();
    var directory = root.resolve("historical").resolve(id.toString()).resolve(lease.toString());
    java.nio.file.Files.createDirectories(directory);
    String source = "PUBLIC_TEST_SOURCE",
        modelHash = json.hash(source),
        placements = "[]",
        output = "{\"test\":true}";
    String inputHash = json.hash(modelHash + "\n" + placements);
    var job =
        new io.waterleague.historical.entity.HistoricalExperiment(
            id,
            owner,
            "11200",
            modelHash,
            inputHash,
            placements,
            "SUCCEEDED",
            lease,
            java.time.Instant.now(),
            output,
            null);
    var values =
        new TreeMap<>(
            Map.of(
                "rainfall-model.json",
                source,
                "historical.py",
                "# 시험 전용\n",
                "result.json",
                output,
                "request.json",
                json.write(
                    Map.of(
                        "modelHash",
                        modelHash,
                        "inputHash",
                        inputHash,
                        "placements",
                        placements))));
    var hashes = new TreeMap<String, String>();
    values.put("sensitivity/sensitivity.json", "{\"test\":\"preserved\"}");
    values.put("pavement-comparison/FRESH.inp", "시험 전용 새 블록 입력");
    values.put("pavement-comparison/DUST_96_G.out", "시험 전용 막힘 출력");
    values.put("pavement-comparison/code/engine/__init__.py", "# 시험 전용\n");
    for (var entry : values.entrySet()) {
      java.nio.file.Files.createDirectories(directory.resolve(entry.getKey()).getParent());
      java.nio.file.Files.writeString(directory.resolve(entry.getKey()), entry.getValue());
      hashes.put(entry.getKey(), json.hash(entry.getValue()));
    }
    java.nio.file.Files.writeString(directory.resolve("manifest.json"), json.write(hashes));
    var artifacts =
        new io.waterleague.historical.service.HistoricalArtifactService(root.toString(), json);
    var names = new ArrayList<String>();
    try (var zip =
        new java.util.zip.ZipInputStream(new java.io.ByteArrayInputStream(artifacts.bundle(job)))) {
      java.util.zip.ZipEntry entry;
      while ((entry = zip.getNextEntry()) != null) names.add(entry.getName());
    }
    assertThat(names)
        .contains(
            "sensitivity/sensitivity.json",
            "pavement-comparison/FRESH.inp",
            "pavement-comparison/DUST_96_G.out",
            "pavement-comparison/code/engine/__init__.py");
    for (String invalid :
        List.of(
            "pavement-comparison/../../outside.py",
            "pavement-comparison/CLEANED.out",
            "pavement-comparison/code/engine/.secret",
            "pavement-comparison/code/engine/run.sh")) {
      hashes.put(invalid, json.hash("시험"));
      java.nio.file.Files.writeString(directory.resolve("manifest.json"), json.write(hashes));
      assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
      hashes.remove(invalid);
    }
    java.nio.file.Files.writeString(directory.resolve("manifest.json"), json.write(hashes));
    java.nio.file.Files.writeString(directory.resolve("sensitivity/sensitivity.json"), "변경된 비교");
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
    java.nio.file.Files.writeString(
        directory.resolve("sensitivity/sensitivity.json"),
        values.get("sensitivity/sensitivity.json"));
    java.nio.file.Files.writeString(directory.resolve("historical.py"), "변경된 입력");
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
    java.nio.file.Files.delete(directory.resolve("historical.py"));
    var outside = root.resolve("outside.py");
    java.nio.file.Files.writeString(outside, values.get("historical.py"));
    java.nio.file.Files.createSymbolicLink(directory.resolve("historical.py"), outside);
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
  }
}
