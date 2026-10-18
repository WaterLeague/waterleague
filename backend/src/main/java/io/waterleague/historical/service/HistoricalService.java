package io.waterleague.historical.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.historical.dto.HistoricalRequest;
import io.waterleague.historical.entity.HistoricalExperiment;
import io.waterleague.historical.repository.HistoricalRepository;
import io.waterleague.historical.view.HistoricalView;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementValidationService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HistoricalService {
  private static final String SENSITIVITY_POLICY = "SELECTED_SURFACE_7_DAY_DRY_WET_V1";
  private static final String SWALE_STATE_POLICY = "SELECTED_SWALE_7_DAY_STATE_V2";
  private final HistoricalRepository jobs;
  private final io.waterleague.budget.service.BudgetService budget;
  private final SimulationRepository admission;
  private final SiteCatalogRepository sites;
  private final DistrictRepository districts;
  private final LabModelRepository models;
  private final PlacementValidationService validation;
  private final JsonService json;
  private final io.waterleague.disaster.service.DisasterService disasters;
  private final io.waterleague.cost.service.CostService costRecords;

  public HistoricalService(
      HistoricalRepository jobs,
      io.waterleague.budget.service.BudgetService budget,
      SimulationRepository admission,
      SiteCatalogRepository sites,
      DistrictRepository districts,
      LabModelRepository models,
      PlacementValidationService validation,
      JsonService json,
      io.waterleague.disaster.service.DisasterService disasters,
      io.waterleague.cost.service.CostService costRecords) {
    this.jobs = jobs;
    this.budget = budget;
    this.admission = admission;
    this.sites = sites;
    this.districts = districts;
    this.models = models;
    this.validation = validation;
    this.json = json;
    this.disasters = disasters;
    this.costRecords = costRecords;
  }

  public HistoricalExperiment require(UUID owner, UUID id) {
    return jobs.get(owner, id).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  public HistoricalView view(HistoricalExperiment j) {
    return new HistoricalView(
        j.id(),
        j.districtId(),
        j.modelHash(),
        j.state(),
        j.createdAt(),
        json.tree(j.placements()),
        j.result() == null ? null : json.tree(j.result()),
        Set.of("FAILED", "REJECTED").contains(j.state())
            ? "계산 입력 또는 물수지 검사로 결과를 게시하지 못했습니다. 다시 계산해 주세요."
            : "");
  }

  public List<HistoricalView> list(UUID owner) {
    return jobs.list(owner).stream().map(this::view).toList();
  }

  @Transactional
  public HistoricalView create(UUID owner, HistoricalRequest dto) {
    if (dto.sensitivityCellId() != null
        && dto.placements().stream().noneMatch(p -> p.cellId().equals(dto.sensitivityCellId())))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var district = districts.require(dto.districtId());
    disasters.requireModel(dto.districtId(), dto.modelHash());
    var model = models.require(dto.modelHash());
    if (!model.model().path("mapId").asString().equals(district.mapId()))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    boolean temporal = dto.temporalPolicy() != null;
    if ((temporal && !dto.temporalPolicy().equals("INSTALLATION_TIME_EXPERIMENT_V1"))
        || (!temporal && dto.parentExperimentId() != null))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var rain = model.model().path("rainfall");
    var start = Instant.parse(rain.path("start").asString());
    var end = Instant.parse(rain.path("end").asString());
    for (var p : dto.placements()) {
      if (temporal
          ? p.installedAt() == null
              || p.installedAt().getNano() != 0
              || p.installedAt().isBefore(start)
              || !p.installedAt().isBefore(end)
          : p.installedAt() != null) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    }
    if (dto.parentExperimentId() != null) {
      var parent = require(owner, dto.parentExperimentId());
      if (!parent.modelHash().equals(dto.modelHash())
          || !parent.districtId().equals(dto.districtId()))
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    }
    var cells = new HashMap<String, PlacementCell>();
    var costs = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    var physical = new ArrayList<Placement>();
    var frozen = new ArrayList<Map<String, Object>>();
    var allocated = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    for (var p :
        dto.placements().stream()
            .sorted(Comparator.comparing(HistoricalRequest.Item::cellId))
            .toList()) {
      var c = sites.require(district.id(), p.cellId());
      var types = new HashSet<FacilityType>();
      for (var t : c.allowedTypes()) types.add(FacilityType.valueOf(t));
      cells.put(
          c.cellId(), new PlacementCell(c.cellId(), types, c.maxAreaFor(p.facilityType()), true));
      c.unitCosts().forEach((t, n) -> costs.put(FacilityType.valueOf(t), n));
      physical.add(new Placement(p.cellId(), p.facilityType(), p.areaM2()));
      var unitCost = c.unitCosts().get(p.facilityType().name());
      if (unitCost == null) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      allocated.merge(p.facilityType(), unitCost.multiply(p.areaM2()).setScale(2), BigDecimal::add);
      frozen.add(
          new TreeMap<>(
              Map.of(
                  "districtId",
                  district.id(),
                  "cellId",
                  c.cellId(),
                  "siteModelHash",
                  c.modelHash(),
                  "facilityType",
                  p.facilityType(),
                  "areaM2",
                  p.areaM2(),
                  "budgetPolicy",
                  budget.policy())));
      if (temporal) {
        frozen.getLast().put("temporalPolicy", dto.temporalPolicy());
        frozen.getLast().put("installedAt", p.installedAt().toString());
      }
    }
    if (dto.parentExperimentId() != null)
      frozen.getFirst().put("parentExperimentId", dto.parentExperimentId().toString());
    var cost = validation.validate(physical, cells, costs, budget.limit(), 50);
    if (cost.compareTo(allocated.values().stream().reduce(BigDecimal.ZERO, BigDecimal::add)) != 0)
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var accounting = budget.validateDesign(allocated);
    frozen.getFirst().put("budgetAccounting", accounting);
    frozen.getFirst().put("publicAssetPolicy", sites.publicAssetPolicy());
    String body = json.write(frozen), hash = json.hash(dto.modelHash() + "\n" + body);
    admission.lockAdmission();
    admission.lockOwner(owner);
    var previous = jobs.byKey(owner, dto.requestKey());
    if (previous.isPresent()) {
      // 원장 추가 전 입력도 같은 사용자 요청이면 기존 실행을 반환한다.
      var old = previous.get();
      var oldPlacements = json.tree(old.placements());
      if (!old.modelHash().equals(dto.modelHash())
          || !old.districtId().equals(dto.districtId())
          || oldPlacements.get(0).has("submissionPolicy")
          || oldPlacements.size() != frozen.size()) throw new DomainException(ErrorCode.CONFLICT);
      for (int n = 0; n < frozen.size(); n++) {
        var entry = oldPlacements.get(n);
        var candidate = frozen.get(n);
        var expected =
            dto.placements().stream()
                .filter(p -> p.cellId().equals(candidate.get("cellId")))
                .findFirst()
                .orElseThrow();
        if (expected.siteModelHash() != null
            && !entry.path("siteModelHash").asString().equals(expected.siteModelHash()))
          throw new DomainException(ErrorCode.CONFLICT);
        for (var field : List.of("temporalPolicy", "installedAt", "parentExperimentId")) {
          if (!Objects.equals(
              entry.has(field) ? entry.path(field).asString() : null, candidate.get(field)))
            throw new DomainException(ErrorCode.CONFLICT);
        }
        boolean requestedSensitivity = candidate.get("cellId").equals(dto.sensitivityCellId());
        if (requestedSensitivity != entry.has("initializationSensitivity")
            || (requestedSensitivity
                && !Set.of(SENSITIVITY_POLICY, SWALE_STATE_POLICY)
                    .contains(entry.path("initializationSensitivity").asString())))
          throw new DomainException(ErrorCode.CONFLICT);
        if (!entry.path("cellId").asString().equals(candidate.get("cellId"))
            || !entry
                .path("facilityType")
                .asString()
                .equals(candidate.get("facilityType").toString())
            || entry.path("areaM2").decimalValue().compareTo((BigDecimal) candidate.get("areaM2"))
                != 0) throw new DomainException(ErrorCode.CONFLICT);
      }
      return view(previous.get());
    }
    // 기존 요청은 원 입력으로 반환하고 새로운 배치만 현재 공개 경계와 대조한다.
    for (var p : dto.placements()) {
      var site = sites.requireInstallable(district.id(), p.cellId());
      if (p.siteModelHash() != null && !site.modelHash().equals(p.siteModelHash()))
        throw new DomainException(ErrorCode.HISTORICAL_SITE_CHANGED);
    }
    for (var row : frozen) {
      var site = sites.require(district.id(), (String) row.get("cellId"));
      if (row.get("cellId").equals(dto.sensitivityCellId())) {
        if (site.initializationPolicy() == null
            || site.initializationPolicy().isNull()
            || site.facilityDesignSet() == null
            || site.facilityDesignSet().isNull())
          throw new DomainException(ErrorCode.SIMULATION_UNAVAILABLE);
        row.put(
            "initializationSensitivity",
            row.get("facilityType") == FacilityType.VEGETATIVE_SWALE
                ? SWALE_STATE_POLICY
                : SENSITIVITY_POLICY);
      }
      var type = (FacilityType) row.get("facilityType");
      var area = (BigDecimal) row.get("areaM2");
      var record =
          costRecords.snapshot(
              site, type, area, site.unitCosts().get(type.name()).multiply(area).setScale(2));
      row.put("costSnapshotRaw", record.raw());
      row.put("costSnapshotSha256", record.sha256());
    }
    body = json.write(frozen);
    hash = json.hash(dto.modelHash() + "\n" + body);
    if (jobs.active(owner) >= 2 || admission.totalActive() >= 20)
      throw new DomainException(ErrorCode.SIMULATION_QUOTA_EXCEEDED);
    var j =
        new HistoricalExperiment(
            UUID.randomUUID(),
            owner,
            district.id(),
            dto.modelHash(),
            hash,
            body,
            "QUEUED",
            null,
            Instant.now(),
            null,
            null);
    jobs.add(j, dto.requestKey());
    return view(j);
  }
}
