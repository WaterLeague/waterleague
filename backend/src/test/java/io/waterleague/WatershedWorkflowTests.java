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
import io.waterleague.watershed.repository.WatershedCostRepository;
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
class WatershedWorkflowTests extends PostgresIntegrationTest {
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

  WatershedRequest.StorageItem tank(String id, String connection, String area, String inletCrest) {
    var coefficient = new BigDecimal("0.650");
    return new WatershedRequest.StorageItem(
        id,
        connection,
        new BigDecimal(area),
        new BigDecimal("16.000"),
        new BigDecimal("5.000"),
        BigDecimal.ZERO,
        new WatershedRequest.Port(
            new BigDecimal(inletCrest), new BigDecimal("0.200"), coefficient, false),
        new WatershedRequest.Port(
            new BigDecimal("16.200"), new BigDecimal("0.030"), coefficient, false),
        new WatershedRequest.Port(
            new BigDecimal("18.500"), new BigDecimal("0.120"), coefficient, false));
  }

  WatershedRequest storageRequest(
      UUID key, List<WatershedRequest.Item> lids, WatershedRequest.StorageItem tank) {
    return new WatershedRequest(
        key,
        WatershedCatalogRepository.HASH,
        lids,
        null,
        new WatershedRequest.StorageRequest(
            WatershedCatalogRepository.STORAGE_HASH, List.of(tank)));
  }

  @Test
  void freezesPublicStorageConnectionsAndCanonicalMixedDesign() {
    assertThat(catalog.storage().path("connections")).hasSize(23);
    UUID key = UUID.randomUUID();
    var job =
        service.create(owner, storageRequest(key, List.of(), tank("Tank1", "C1", "100", "18.5")));
    var storage = job.design().path("storage");
    assertThat(job.design().path("placements")).isEmpty();
    assertThat(storage.path("placements").get(0).path("inlet").path("nodeId").asString())
        .isEqualTo("J1");
    assertThat(storage.path("placements").get(0).path("drain").path("nodeId").asString())
        .isEqualTo("J2");
    assertThat(storage.path("sourceNetworkSha256").asString())
        .isEqualTo(catalog.storage().path("baseNetworkSha256").asString());
    assertThat(
            service
                .create(
                    owner, storageRequest(key, List.of(), tank("Tank1", "C1", "100.00", "18.500")))
                .id())
        .isEqualTo(job.id());
    assertThatThrownBy(
            () ->
                service.create(
                    owner, storageRequest(key, List.of(), tank("Tank1", "C1", "101", "18.5"))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    var lids = request(UUID.randomUUID(), "Bio1", "S1", "100", "1000").placements();
    var mixed =
        service.create(
            owner, storageRequest(UUID.randomUUID(), lids, tank("Tank1", "C1", "100", "18.5")));
    assertThat(mixed.design().path("placements")).hasSize(1);
    assertThat(mixed.design().path("storage").path("placements")).hasSize(1);
    assertThatThrownBy(() -> service.require(UUID.randomUUID(), job.id()))
        .isInstanceOf(DomainException.class);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void rejectsForeignStorageConnectionsOutOfRangePortsAndSharedIdentifiers() {
    for (var t :
        List.of(
            tank("Tank1", "OUT1", "100", "18.5"),
            tank("Tank1", "C1", "100", "17"),
            tank("Tank1", "C1", "100", "22")))
      assertThatThrownBy(
              () -> service.create(owner, storageRequest(UUID.randomUUID(), List.of(), t)))
          .isInstanceOf(DomainException.class);
    var lids = request(UUID.randomUUID(), "Tank1", "S1", "100", "1000").placements();
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    storageRequest(UUID.randomUUID(), lids, tank("tank1", "C1", "100", "18.5"))))
        .isInstanceOf(DomainException.class);
    try (var factory = jakarta.validation.Validation.buildDefaultValidatorFactory()) {
      assertThat(
              factory
                  .getValidator()
                  .validate(
                      storageRequest(
                          UUID.randomUUID(), List.of(), tank("Tank1", "C1", "100.001", "18.5"))))
          .isNotEmpty();
    }
    assertThat(service.list(owner)).isEmpty();
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
  void freezesCisternQuotesWithoutChangingPhysicalDesignOrBudget() throws Exception {
    var fixture =
        json.tree(
            Files.readString(Path.of("../simulation/tests/fixtures/member-cistern-costs-v1.json")));
    var placements =
        List.of(
            new WatershedRequest.Item(
                "Cistern1",
                "S1",
                "RAINWATER_CISTERN",
                new BigDecimal("2.35"),
                new BigDecimal("235")),
            new WatershedRequest.Item(
                "Cistern2", "S1", "RAINWATER_CISTERN", BigDecimal.ONE, new BigDecimal("235")));
    UUID key = UUID.randomUUID();
    var dto =
        new WatershedRequest(
            key,
            WatershedCatalogRepository.HASH,
            placements,
            null,
            null,
            null,
            WatershedCostRepository.CISTERN_HASH);
    var job = service.create(owner, dto);
    assertThat(job.design().path("cisternCosting")).isEqualTo(fixture.path("cisternCosting"));
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThatThrownBy(
            () ->
                service.create(
                    owner, new WatershedRequest(key, WatershedCatalogRepository.HASH, placements)))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThat(service.catalog()).containsKey("cisternCostCatalog");
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
    Path output = Path.of("../tmp/cistern-server-request.json");
    var stored = service.require(owner, job.id());
    Files.writeString(
        output,
        json.write(
            Map.of(
                "modelHash",
                stored.modelHash(),
                "inputHash",
                stored.inputHash(),
                "placements",
                stored.placements())));
  }

  @Test
  void rejectsCisternCostCatalogMismatchAndUnrelatedFacilities() {
    var lids = request(UUID.randomUUID(), "Bio1", "S1", "100", "1000").placements();
    for (String hash : List.of(WatershedCostRepository.CISTERN_HASH, "0".repeat(64)))
      assertThatThrownBy(
              () ->
                  service.create(
                      owner,
                      new WatershedRequest(
                          UUID.randomUUID(),
                          WatershedCatalogRepository.HASH,
                          lids,
                          null,
                          null,
                          null,
                          hash)))
          .isInstanceOf(DomainException.class);
    assertThat(service.list(owner)).isEmpty();
  }

  WatershedRequest.ConduitItem pipe(String id, String conduit, String width) {
    return new WatershedRequest.ConduitItem(
        id,
        conduit,
        "RECT_CLOSED",
        new BigDecimal("2.2"),
        new BigDecimal(width),
        1,
        new BigDecimal("0.0147"));
  }

  WatershedRequest pipeRequest(UUID key, List<WatershedRequest.ConduitItem> pipes) {
    return new WatershedRequest(
        key,
        WatershedCatalogRepository.HASH,
        List.of(),
        null,
        null,
        new WatershedRequest.ConduitRequest(WatershedCatalogRepository.CONDUIT_HASH, pipes));
  }

  @Test
  void freezesConduitOriginalAndKeepsCanonicalRequestsAndOwnerBoundary() {
    assertThat(catalog.conduits().path("conduits")).hasSize(26);
    UUID key = UUID.randomUUID();
    var dto = pipeRequest(key, List.of(pipe("Pipe1", "C2", "3")));
    var job = service.create(owner, dto);
    var p = job.design().path("conduits").path("placements").get(0);
    assertThat(p.path("original").path("widthM").doubleValue()).isEqualTo(2.2);
    assertThat(p.path("widthM").doubleValue()).isEqualTo(3);
    assertThat(job.design().path("costing").isMissingNode()).isTrue();
    assertThat(service.create(owner, pipeRequest(key, List.of(pipe("Pipe1", "C2", "3.000")))).id())
        .isEqualTo(job.id());
    assertThatThrownBy(
            () -> service.create(owner, pipeRequest(key, List.of(pipe("Pipe1", "C2", "4")))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThatThrownBy(() -> service.require(UUID.randomUUID(), job.id()))
        .isInstanceOf(DomainException.class);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void rejectsConduitDuplicationForeignLinksAndIdentifiersSharedWithStorage() {
    for (var pipes :
        List.of(
            List.of(pipe("Pipe1", "NONE", "3")),
            List.of(pipe("Pipe1", "C2", "3"), pipe("Pipe2", "C2", "4"))))
      assertThatThrownBy(() -> service.create(owner, pipeRequest(UUID.randomUUID(), pipes)))
          .isInstanceOf(DomainException.class);
    var storage =
        storageRequest(UUID.randomUUID(), List.of(), tank("Pipe1", "C1", "100", "18.5")).storage();
    var mixed =
        new WatershedRequest(
            UUID.randomUUID(),
            WatershedCatalogRepository.HASH,
            List.of(),
            null,
            storage,
            new WatershedRequest.ConduitRequest(
                WatershedCatalogRepository.CONDUIT_HASH, List.of(pipe("pipe1", "C2", "3"))));
    assertThatThrownBy(() -> service.create(owner, mixed)).isInstanceOf(DomainException.class);
    var invalid =
        new WatershedRequest.ConduitItem(
            "Pipe1",
            "C2",
            "CIRCULAR",
            new BigDecimal("2.2"),
            new BigDecimal("3"),
            1,
            new BigDecimal(".0147"));
    assertThatThrownBy(
            () -> service.create(owner, pipeRequest(UUID.randomUUID(), List.of(invalid))))
        .isInstanceOf(DomainException.class);
    var tooHigh =
        new WatershedRequest.ConduitItem(
            "Pipe1",
            "C2",
            "RECT_CLOSED",
            new BigDecimal("3.201"),
            new BigDecimal("3"),
            1,
            new BigDecimal(".0147"));
    assertThatThrownBy(
            () -> service.create(owner, pipeRequest(UUID.randomUUID(), List.of(tooHigh))))
        .isInstanceOf(DomainException.class);
    assertThat(service.list(owner)).isEmpty();
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
  void freezesReferenceCostAndKeepsUnknownPricesAndLegacyRequests() {
    var placements =
        List.of(
            new WatershedRequest.Item(
                "Bio1", "S1", "BIORETENTION", new BigDecimal("100.01"), BigDecimal.ZERO),
            new WatershedRequest.Item(
                "Swale1", "S1", "VEGETATIVE_SWALE", new BigDecimal("100"), BigDecimal.ZERO));
    var key = UUID.randomUUID();
    var dto =
        new WatershedRequest(
            key, WatershedCatalogRepository.HASH, placements, WatershedCostRepository.HASH);
    var job = service.create(owner, dto);
    var cost = job.design().path("costing");
    assertThat(cost.path("knownReferenceSubtotalKrw").longValue()).isEqualTo(56005600);
    assertThat(cost.path("items").get(1).path("referenceAmountKrw").isNull()).isTrue();
    assertThat(cost.path("unpricedPlacementIds").get(0).asString()).isEqualTo("Swale1");
    assertThat(cost.path("completeInstalledCostKrw").isNull()).isTrue();
    assertThat(cost.path("budgetChargedKrw").isNull()).isTrue();
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThatThrownBy(
            () -> service.create(owner, new WatershedRequest(key, dto.catalogHash(), placements)))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new WatershedRequest(
                        UUID.randomUUID(), dto.catalogHash(), placements, "0".repeat(64))))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.CONFLICT));
    var old = service.create(owner, request(UUID.randomUUID(), "Bio1", "S1", "100", "0"));
    assertThat(old.design().path("costing").isMissingNode()).isTrue();
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

  WatershedRequest.PumpItem pump(String id, String from, String to) {
    return new WatershedRequest.PumpItem(
        id,
        from,
        to,
        new BigDecimal("1.800"),
        new BigDecimal("1.200"),
        "OFF",
        new WatershedRequest.PumpDelivery(
            new BigDecimal("10"),
            new BigDecimal("0.5"),
            new BigDecimal("0.1"),
            new BigDecimal("20"),
            new BigDecimal("0.5"),
            BigDecimal.ONE,
            BigDecimal.ZERO,
            true));
  }

  WatershedRequest pumpRequest(UUID key, List<WatershedRequest.PumpItem> pumps) {
    var t = tank("Tank", "C1", "100", "18.5");
    var deep =
        new WatershedRequest.StorageItem(
            t.id(),
            t.connectionId(),
            t.areaM2(),
            new BigDecimal("12"),
            new BigDecimal("9"),
            t.initialDepthM(),
            t.inlet(),
            t.drain(),
            t.overflow());
    return new WatershedRequest(
        key,
        WatershedCatalogRepository.HASH,
        List.of(),
        null,
        new WatershedRequest.StorageRequest(WatershedCatalogRepository.STORAGE_HASH, List.of(deep)),
        null,
        null,
        new WatershedRequest.PumpRequest(WatershedCatalogRepository.PUMP_HASH, pumps));
  }

  @Test
  void bindsPumpCurveConnectionsControlsAndCanonicalOwnerRequest() throws Exception {
    var dto = pumpRequest(UUID.randomUUID(), List.of(pump("Pump1", "WLST_Tank", "J2")));
    var job = service.create(owner, dto);
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    var row = job.design().path("pumps").path("placements").get(0);
    assertThat(row.path("curveId").asString()).isEqualTo("KSB_PA4_500_270_1450_17_V1");
    assertThat(row.path("fromNode").asString()).isEqualTo("WLST_Tank");
    assertThat(row.path("delivery").path("checkValve").asBoolean()).isTrue();
    assertThat(service.catalog())
        .containsEntry("pumpCatalogHash", WatershedCatalogRepository.PUMP_HASH);
    assertThatThrownBy(() -> service.require(UUID.randomUUID(), job.id()))
        .isInstanceOf(DomainException.class);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
    var stored = service.require(owner, job.id());
    Files.writeString(
        Path.of("../tmp/pump-server-request.json"),
        json.write(
            Map.of(
                "modelHash",
                stored.modelHash(),
                "inputHash",
                stored.inputHash(),
                "placements",
                stored.placements())));
  }

  @Test
  void rejectsUnknownPumpNodesUpstreamTransfersDuplicatePairsAndSharedIdentifiers() {
    for (var rows :
        List.of(
            List.of(pump("Pump1", "UNKNOWN", "J2")),
            List.of(pump("Pump1", "WLST_Tank", "Out1")),
            List.of(pump("Pump1", "J2", "J1")),
            List.of(pump("tank", "WLST_Tank", "J2")),
            List.of(pump("Pump1", "WLST_Tank", "J2"), pump("Pump2", "WLST_Tank", "J2")))) {
      assertThatThrownBy(() -> service.create(owner, pumpRequest(UUID.randomUUID(), rows)))
          .isInstanceOf(DomainException.class);
    }
    var dto = pumpRequest(UUID.randomUUID(), List.of(pump("Pump1", "WLST_Tank", "J2")));
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new WatershedRequest(
                        dto.requestKey(),
                        dto.catalogHash(),
                        dto.placements(),
                        null,
                        null,
                        null,
                        null,
                        dto.pumps())))
        .isInstanceOf(DomainException.class);
    assertThat(service.list(owner)).isEmpty();
  }

  WatershedRequest.CisternItem hydraulicCistern(String id, String host, String capture) {
    return new WatershedRequest.CisternItem(
        id,
        host,
        new BigDecimal(capture),
        new BigDecimal("2.35"),
        new BigDecimal("12.750"),
        new BigDecimal("2.000"),
        BigDecimal.ZERO,
        new WatershedRequest.Port(
            new BigDecimal("12.800"), new BigDecimal("0.040"), new BigDecimal("0.650"), true),
        new WatershedRequest.Port(
            new BigDecimal("14.300"), new BigDecimal("0.200"), new BigDecimal("0.650"), true));
  }

  @Test
  void preservesHydraulicCisternRequestAndCapacityQuoteWithOtherCatchmentLid() throws Exception {
    var item = hydraulicCistern("Cistern1", "S9", "10");
    var dto =
        new WatershedRequest(
            UUID.randomUUID(),
            WatershedCatalogRepository.HASH,
            request(UUID.randomUUID(), "Bio1", "S1", "20", "100").placements(),
            WatershedCostRepository.HASH,
            null,
            null,
            WatershedCostRepository.CISTERN_HASH,
            null,
            new WatershedRequest.CisternRequest(WatershedCatalogRepository.STORAGE_HASH, item));
    var job = service.create(owner, dto);
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    assertThat(job.design().path("cistern").path("subcatchmentId").asString()).isEqualTo("S9");
    assertThat(
            job.design()
                .path("cisternCosting")
                .path("items")
                .get(0)
                .path("capacityM3")
                .decimalValue())
        .isEqualByComparingTo("4.7");
    assertThat(
            job.design()
                .path("cisternCosting")
                .path("items")
                .get(0)
                .path("equivalentUnits")
                .asInt())
        .isEqualTo(2);
    var stored = service.require(owner, job.id());
    Files.writeString(
        Path.of("../tmp/cistern-hydraulic-server-request.json"),
        json.write(
            Map.of(
                "modelHash",
                stored.modelHash(),
                "inputHash",
                stored.inputHash(),
                "placements",
                stored.placements())));
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM budget_ledger_entries WHERE owner_id=?",
                Integer.class,
                owner))
        .isZero();
  }

  @Test
  void preservesMixedSurfaceCisternAndRejectsPerviousCapture() throws Exception {
    var source = hydraulicCistern("Cistern1", "S1", "10");
    var item =
        new WatershedRequest.CisternItem(
            source.id(),
            source.catchmentId(),
            source.captureAreaM2(),
            source.areaM2(),
            new BigDecimal("16.480"),
            source.depthM(),
            source.initialDepthM(),
            new WatershedRequest.Port(
                new BigDecimal("16.530"), new BigDecimal("0.040"), new BigDecimal("0.650"), true),
            new WatershedRequest.Port(
                new BigDecimal("18.030"), new BigDecimal("0.200"), new BigDecimal("0.650"), true));
    var dto =
        new WatershedRequest(
            UUID.randomUUID(),
            WatershedCatalogRepository.HASH,
            List.of(),
            null,
            null,
            null,
            WatershedCostRepository.CISTERN_HASH,
            null,
            new WatershedRequest.CisternRequest(WatershedCatalogRepository.STORAGE_HASH, item));
    var job = service.create(owner, dto);
    assertThat(job.design().path("cistern").path("schemaVersion").asInt()).isEqualTo(2);
    assertThat(service.create(owner, dto).id()).isEqualTo(job.id());
    var stored = service.require(owner, job.id());
    Files.writeString(
        Path.of("../tmp/cistern-mixed-server-request.json"),
        json.write(
            Map.of(
                "modelHash",
                stored.modelHash(),
                "inputHash",
                stored.inputHash(),
                "placements",
                stored.placements())));
    var excess =
        new WatershedRequest.CisternItem(
            item.id(),
            item.catchmentId(),
            new BigDecimal("30000"),
            item.areaM2(),
            item.invertM(),
            item.depthM(),
            item.initialDepthM(),
            item.drain(),
            item.overflow());
    assertThatThrownBy(
            () ->
                service.create(
                    owner,
                    new WatershedRequest(
                        UUID.randomUUID(),
                        WatershedCatalogRepository.HASH,
                        List.of(),
                        null,
                        null,
                        null,
                        null,
                        null,
                        new WatershedRequest.CisternRequest(
                            WatershedCatalogRepository.STORAGE_HASH, excess))))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void rejectsCisternSharedCatchmentAreaOverflowAndDuplicateIds() {
    for (var p :
        List.of(
            hydraulicCistern("Cistern1", "S1", "10"),
            hydraulicCistern("Cistern1", "S9", "13729.38"),
            hydraulicCistern("Bio1", "S9", "10"))) {
      var dto =
          new WatershedRequest(
              UUID.randomUUID(),
              WatershedCatalogRepository.HASH,
              request(UUID.randomUUID(), "Bio1", "S1", "20", "100").placements(),
              null,
              null,
              null,
              null,
              null,
              new WatershedRequest.CisternRequest(WatershedCatalogRepository.STORAGE_HASH, p));
      assertThatThrownBy(() -> service.create(owner, dto)).isInstanceOf(DomainException.class);
    }
    var shared =
        new WatershedRequest(
            UUID.randomUUID(),
            WatershedCatalogRepository.HASH,
            request(UUID.randomUUID(), "Bio1", "S9", "20", "100").placements(),
            null,
            null,
            null,
            null,
            null,
            new WatershedRequest.CisternRequest(
                WatershedCatalogRepository.STORAGE_HASH, hydraulicCistern("Cistern1", "S9", "10")));
    assertThatThrownBy(() -> service.create(owner, shared)).isInstanceOf(DomainException.class);
    assertThat(service.list(owner)).isEmpty();
  }
}
