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
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class HistoricalWorkflowTests {
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
            "2410520",
            "AFFILIATED"));
    hash =
        disasters.catalog().events().getFirst().regions().stream()
            .filter(r -> r.districtId().equals("2419953"))
            .findFirst()
            .orElseThrow()
            .modelHash();
    cell =
        sites.district("2419953").keySet().stream()
            .filter(id -> id.startsWith("RW"))
            .findFirst()
            .orElseThrow();
  }

  HistoricalRequest request(UUID key, String id, FacilityType type, String amount) {
    return new HistoricalRequest(
        key,
        "2419953",
        hash,
        List.of(new HistoricalRequest.Item(id, type, new BigDecimal(amount))));
  }

  @Test
  void newHistoricalDesignRejectsCurrentMappedBasinButExistingRequestRemainsReplayable() {
    String district = "2419954";
    String model =
        disasters.catalog().events().getFirst().regions().stream()
            .filter(r -> r.districtId().equals(district))
            .findFirst()
            .orElseThrow()
            .modelHash();
    var key = UUID.randomUUID();
    var blocked =
        new HistoricalRequest(
            key,
            district,
            model,
            List.of(
                new HistoricalRequest.Item(
                    "G20695-54482", FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE)));
    assertThatThrownBy(() -> service.create(owner, blocked))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.EXISTING_INFRASTRUCTURE));
    assertThat(service.list(owner)).isEmpty();
    var site =
        sites.district(district).values().stream()
            .filter(
                s ->
                    s.existingInfrastructure() == null
                        && s.allowedTypes().contains("PERMEABLE_PAVEMENT"))
            .findFirst()
            .orElseThrow();
    var job =
        service.create(
            owner,
            new HistoricalRequest(
                key,
                district,
                model,
                List.of(
                    new HistoricalRequest.Item(
                        site.cellId(), FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE))));
    var old = json.tree(service.require(owner, job.id()).placements());
    var row = (tools.jackson.databind.node.ObjectNode) old.get(0);
    row.put("cellId", "G20695-54482");
    row.remove("publicAssetPolicy");
    String body = json.write(old), oldHash = json.hash(model + "\n" + body);
    db.update(
        "UPDATE historical_experiments SET placements=?,input_hash=? WHERE id=?",
        body,
        oldHash,
        job.id());
    assertThat(service.create(owner, blocked).id()).isEqualTo(job.id());
    assertThat(service.require(owner, job.id()).placements()).isEqualTo(body);
    assertThat(service.require(owner, job.id()).inputHash()).isEqualTo(oldHash);
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
            "SEOUL_RAINWATER_ACCOUNTING_V1",
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
            districts.require("2410520").modelHash(),
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
                        "2419953",
                        hash,
                        List.of(dto.placements().getFirst(), dto.placements().getFirst()))))
        .isInstanceOf(DomainException.class);
    var largeRoofs =
        sites.district("2419953").values().stream()
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
                    owner, new HistoricalRequest(UUID.randomUUID(), "2419953", hash, largeRoofs)))
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
            "2419953",
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
    assertThat(names).contains("sensitivity/sensitivity.json");
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
