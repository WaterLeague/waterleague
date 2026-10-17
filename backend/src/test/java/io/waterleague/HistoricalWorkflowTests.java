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
  void acceptsExpandedSitesAndOtherDistrictsWithoutChangingSharedOccupancy() {
    int before = db.queryForObject("SELECT COUNT(*) FROM shared_installations", Integer.class);
    UUID key = UUID.randomUUID();
    var dto = request(key, cell, FacilityType.GREEN_ROOF, "1.00");
    var job = service.create(owner, dto);
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThat(service.require(owner, job.id()).placements())
        .contains(
            cell, "siteModelHash", "budgetPolicy", "SEOUL_PERSONAL_FULL_2026_V3", "2000000000");
    assertThat(service.list(owner)).hasSize(1);
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
    for (var entry : values.entrySet()) {
      java.nio.file.Files.writeString(directory.resolve(entry.getKey()), entry.getValue());
      hashes.put(entry.getKey(), json.hash(entry.getValue()));
    }
    java.nio.file.Files.writeString(directory.resolve("manifest.json"), json.write(hashes));
    var artifacts =
        new io.waterleague.historical.service.HistoricalArtifactService(root.toString(), json);
    assertThat(artifacts.bundle(job)).isNotEmpty();
    java.nio.file.Files.writeString(directory.resolve("historical.py"), "변경된 입력");
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
    java.nio.file.Files.delete(directory.resolve("historical.py"));
    var outside = root.resolve("outside.py");
    java.nio.file.Files.writeString(outside, values.get("historical.py"));
    java.nio.file.Files.createSymbolicLink(directory.resolve("historical.py"), outside);
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
  }
}
