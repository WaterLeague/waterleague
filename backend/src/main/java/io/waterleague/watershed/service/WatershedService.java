package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.entity.WatershedExperiment;
import io.waterleague.watershed.repository.*;
import io.waterleague.watershed.view.WatershedView;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

@Service
public class WatershedService {
  private final WatershedRepository jobs;
  private final WatershedCatalogRepository catalog;
  private final SimulationRepository admission;
  private final JsonService json;
  private final WatershedCostRepository costCatalog;
  private final WatershedCostService costs;
  private final StorageDesignService storage;
  private final ConduitDesignService conduits;
  private final PumpDesignService pumps;

  public WatershedService(
      WatershedRepository jobs,
      WatershedCatalogRepository catalog,
      SimulationRepository admission,
      JsonService json,
      WatershedCostRepository costCatalog,
      WatershedCostService costs,
      StorageDesignService storage,
      ConduitDesignService conduits,
      PumpDesignService pumps) {
    this.jobs = jobs;
    this.catalog = catalog;
    this.admission = admission;
    this.json = json;
    this.costCatalog = costCatalog;
    this.costs = costs;
    this.storage = storage;
    this.conduits = conduits;
    this.pumps = pumps;
  }

  public Map<String, Object> catalog() {
    var result = new TreeMap<String, Object>();
    result.put("pumpCatalogHash", WatershedCatalogRepository.PUMP_HASH);
    result.put("pumpCatalog", catalog.pumps());
    result.put("catalogHash", WatershedCatalogRepository.HASH);
    result.put("catalog", catalog.value());
    result.put("costCatalogHash", WatershedCostRepository.HASH);
    result.put("costCatalog", costCatalog.value());
    result.put("layoutHash", WatershedCatalogRepository.LAYOUT_HASH);
    result.put("layout", catalog.layout());
    result.put("storageCatalogHash", WatershedCatalogRepository.STORAGE_HASH);
    result.put("storageCatalog", catalog.storage());
    result.put("conduitCatalogHash", WatershedCatalogRepository.CONDUIT_HASH);
    result.put("conduitCatalog", catalog.conduits());
    result.put("cisternCostCatalogHash", WatershedCostRepository.CISTERN_HASH);
    result.put("cisternCostCatalog", costCatalog.cistern());
    return result;
  }

  public WatershedExperiment require(UUID owner, UUID id) {
    return jobs.get(owner, id).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  public WatershedView view(WatershedExperiment j) {
    return new WatershedView(
        j.id(),
        j.modelHash(),
        j.state(),
        j.createdAt(),
        json.tree(j.placements()),
        j.result() == null ? null : json.tree(j.result()),
        Set.of("FAILED", "REJECTED").contains(j.state())
            ? "공개 관망 계산을 완료하지 못했습니다. 입력과 계산 상태를 확인해 주세요."
            : "");
  }

  public List<WatershedView> list(UUID owner) {
    return jobs.list(owner).stream().map(this::view).toList();
  }

  @Transactional
  public WatershedView create(UUID owner, WatershedRequest dto) {
    if (!WatershedCatalogRepository.HASH.equals(dto.catalogHash()))
      throw new DomainException(ErrorCode.CONFLICT);
    var data = catalog.value();
    Map<String, JsonNode> catchments = new HashMap<>();
    data.path("catchments").forEach(c -> catchments.put(c.path("id").asString(), c));
    var ids = new HashSet<String>();
    var areas = new HashMap<String, BigDecimal>();
    var treated = new HashMap<String, BigDecimal>();
    var placements = new ArrayList<Map<String, Object>>();
    int storageCount =
        dto.storage() == null || dto.storage().placements() == null
            ? 0
            : dto.storage().placements().size();
    int conduitCount =
        dto.conduits() == null || dto.conduits().placements() == null
            ? 0
            : dto.conduits().placements().size();
    int pumpCount = dto.pumps() == null ? 0 : dto.pumps().placements().size();
    int cisternCount = dto.cistern() == null ? 0 : 1;
    if (dto.placements() == null
        || dto.placements().size() + storageCount + conduitCount + pumpCount + cisternCount < 1
        || dto.placements().size() + storageCount + conduitCount + pumpCount + cisternCount > 20)
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    for (var p :
        dto.placements().stream()
            .sorted(Comparator.comparing(WatershedRequest.Item::id))
            .toList()) {
      var template = data.path("templates").path(p.facilityType());
      if (!ids.add(p.id().toUpperCase(Locale.ROOT))
          || !p.id().matches("[A-Za-z][A-Za-z0-9_-]{0,23}")
          || !catchments.containsKey(p.catchmentId())
          || template.isMissingNode()
          || p.areaM2().signum() <= 0
          || p.treatedImperviousM2().signum() < 0
          || p.areaM2().scale() > 2
          || p.treatedImperviousM2().scale() > 2)
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      areas.merge(p.catchmentId(), p.areaM2(), BigDecimal::add);
      treated.merge(p.catchmentId(), p.treatedImperviousM2(), BigDecimal::add);
      placements.add(
          new TreeMap<>(
              Map.of(
                  "id",
                  p.id(),
                  "facilityType",
                  p.facilityType(),
                  "subcatchmentId",
                  p.catchmentId(),
                  "areaM2",
                  p.areaM2().setScale(2),
                  "replacedImperviousM2",
                  p.areaM2().setScale(2),
                  "treatedImperviousM2",
                  p.treatedImperviousM2().setScale(2),
                  "initialSaturationPercent",
                  template.path("initialSaturationPercent"),
                  "parameters",
                  template.path("parameters"))));
    }
    areas.forEach(
        (id, used) -> {
          var c = catchments.get(id);
          if (used.compareTo(c.path("imperviousM2").decimalValue()) > 0
              || used.compareTo(c.path("areaM2").decimalValue().multiply(new BigDecimal("0.999")))
                  > 0
              || treated.get(id).compareTo(c.path("imperviousM2").decimalValue().subtract(used))
                  > 0) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
        });
    var design =
        new TreeMap<String, Object>(
            Map.of(
                "schemaVersion",
                1,
                "basis",
                data.path("designBasis").asString(),
                "placements",
                placements));
    if (dto.storage() != null) design.put("storage", storage.compile(dto.storage(), ids));
    if (dto.conduits() != null) design.put("conduits", conduits.compile(dto.conduits(), ids));
    if (dto.pumps() != null) design.put("pumps", pumps.compile(dto.pumps(), dto.storage(), ids));
    if (dto.cistern() != null)
      design.put(
          "cistern", CisternDesignService.compile(dto.cistern(), catalog, ids, dto.placements()));
    if (dto.costCatalogHash() != null && !dto.placements().isEmpty())
      design.put("costing", costs.snapshot(dto.costCatalogHash(), dto.placements()));
    if (dto.cisternCostCatalogHash() != null)
      design.put(
          "cisternCosting",
          CisternReferenceService.snapshot(
              dto.cisternCostCatalogHash(), placements, costCatalog.cistern(), dto.cistern()));
    String body = json.write(design);
    String hash = json.hash(dto.catalogHash() + "\n" + body);
    admission.lockAdmission();
    admission.lockOwner(owner);
    var old = jobs.byKey(owner, dto.requestKey());
    if (old.isPresent()) {
      if (!old.get().inputHash().equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
      return view(old.get());
    }
    if (jobs.active(owner) >= 2 || admission.totalActive() >= 20)
      throw new DomainException(ErrorCode.SIMULATION_QUOTA_EXCEEDED);
    var job =
        new WatershedExperiment(
            UUID.randomUUID(),
            owner,
            dto.catalogHash(),
            hash,
            body,
            "QUEUED",
            null,
            Instant.now(),
            null);
    jobs.add(job, dto.requestKey());
    return view(job);
  }
}
