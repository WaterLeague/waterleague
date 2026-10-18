package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.entity.WatershedExperiment;
import io.waterleague.watershed.repository.WatershedCatalogRepository;
import io.waterleague.watershed.service.*;
import java.math.BigDecimal;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class WatershedWorkflowTests {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired AccountRepository accounts;
  @Autowired WatershedService service;
  @Autowired WatershedCatalogRepository catalog;
  @Autowired SimulationRepository admission;
  @Autowired JsonService json;
  @Autowired JdbcTemplate db;
  UUID owner;

  @BeforeEach
  void prepare() {
    db.update("DELETE FROM watershed_experiments");
    owner = UUID.randomUUID();
    accounts.add(
        new Account(
            owner,
            "watershed_" + owner.toString().substring(0, 8),
            "관망 시험",
            "NOT_A_LOGIN",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            "2419953",
            "AFFILIATED"));
  }

  WatershedRequest request(UUID key, String id, String catchment, String area, String treated) {
    return new WatershedRequest(
        key,
        WatershedCatalogRepository.HASH,
        List.of(
            new WatershedRequest.Item(
                id, catchment, "BIORETENTION", new BigDecimal(area), new BigDecimal(treated))));
  }

  @Test
  void freezesSourceTemplatesAndUsesSharedAdmissionWithOwnerBoundary() {
    int count = admission.totalActive();
    var dto = request(UUID.randomUUID(), "Bio1", "S1", "100", "1000");
    var job = service.create(owner, dto);
    var stored = service.require(owner, job.id());
    assertThat(stored.inputHash())
        .isEqualTo(json.hash(stored.modelHash() + "\n" + stored.placements()));
    assertThat(stored.placements())
        .contains(
            "soilDepthMm",
            "nativeSeepageBasis",
            "parameters",
            "PUBLIC_REFERENCE_DESIGN_NOT_SITE_MEASURED");
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThat(
            service
                .create(owner, request(dto.requestKey(), "Bio1", "S1", "100.00", "1000.00"))
                .id())
        .isEqualTo(job.id());
    assertThat(admission.totalActive()).isEqualTo(count + 1);
    assertThatThrownBy(() -> service.require(UUID.randomUUID(), job.id()))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    assertThatThrownBy(
            () -> service.create(owner, request(dto.requestKey(), "Bio1", "S1", "101", "1000")))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    service.create(owner, request(UUID.randomUUID(), "Bio2", "S1", "100", "1000"));
    assertThatThrownBy(
            () -> service.create(owner, request(UUID.randomUUID(), "Bio3", "S1", "100", "1000")))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.SIMULATION_QUOTA_EXCEEDED));
    assertThat(admission.totalActive()).isEqualTo(count + 2);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void rejectsMissingCatchmentsDuplicatesAndOverlappingCaptureAreas() {
    assertThat(catalog.value().path("catchments")).hasSize(14);
    assertThat(catalog.value().path("rankingEligible").asBoolean()).isFalse();
    for (var dto :
        List.of(
            request(UUID.randomUUID(), "Bio1", "NONE", "100", "1000"),
            request(UUID.randomUUID(), "Bio1", "S1", "1000000", "0"),
            request(UUID.randomUUID(), "Bio1", "S1", "100", "1000000")))
      assertThatThrownBy(() -> service.create(owner, dto)).isInstanceOf(DomainException.class);
    var one = request(UUID.randomUUID(), "Bio1", "S1", "100", "1000");
    var duplicate =
        new WatershedRequest(
            UUID.randomUUID(),
            one.catalogHash(),
            List.of(one.placements().getFirst(), one.placements().getFirst()));
    assertThatThrownBy(() -> service.create(owner, duplicate)).isInstanceOf(DomainException.class);
    assertThat(service.list(owner)).isEmpty();
  }

  @Test
  void bindsExportedFilesToDatabaseResultAndRejectsLinks(
      @org.junit.jupiter.api.io.TempDir Path root) throws Exception {
    root = root.toRealPath();
    UUID id = UUID.randomUUID(), lease = UUID.randomUUID();
    Path dir = root.resolve("watersheds").resolve(id.toString()).resolve(lease.toString());
    Files.createDirectories(dir);
    String catalogRaw = "PUBLIC_CATALOG",
        model = json.hash(catalogRaw),
        design = "{}",
        input = json.hash(model + "\n" + design);
    var files = new TreeMap<String, String>();
    files.put(
        "request.json",
        json.write(Map.of("modelHash", model, "inputHash", input, "placements", design)));
    files.put("catalog.json", catalogRaw);
    for (String name :
        List.of(
            "original.inp",
            "implementation.zip",
            "engine.bin",
            "engine-build.json",
            "engine-source.tar.gz",
            "baseline/network.rpt")) files.put(name, "검증용 " + name);
    var hashes = new TreeMap<String, String>();
    files.forEach((name, raw) -> hashes.put(name, json.hash(raw)));
    String output = json.write(Map.of("artifactFiles", hashes));
    files.put("result.json", output);
    hashes.put("result.json", json.hash(output));
    for (var f : files.entrySet()) {
      Path path = dir.resolve(f.getKey());
      Files.createDirectories(path.getParent());
      Files.writeString(path, f.getValue());
    }
    Files.writeString(dir.resolve("manifest.json"), json.write(hashes));
    var job =
        new WatershedExperiment(
            id, owner, model, input, design, "SUCCEEDED", lease, Instant.now(), output);
    var artifacts = new WatershedArtifactService(root.toString(), json);
    assertThat(artifacts.bundle(job)).isNotEmpty();
    Files.writeString(dir.resolve("engine.bin"), "변조");
    hashes.put("engine.bin", json.hash("변조"));
    Files.writeString(dir.resolve("manifest.json"), json.write(hashes));
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
    Files.writeString(dir.resolve("engine.bin"), files.get("engine.bin"));
    hashes.put("engine.bin", json.hash(files.get("engine.bin")));
    Files.writeString(dir.resolve("manifest.json"), json.write(hashes));
    Files.delete(dir.resolve("engine.bin"));
    Files.writeString(root.resolve("outside.bin"), files.get("engine.bin"));
    Files.createSymbolicLink(dir.resolve("engine.bin"), root.resolve("outside.bin"));
    assertThatThrownBy(() -> artifacts.bundle(job)).isInstanceOf(DomainException.class);
  }
}
