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
  private final HistoricalRepository jobs;
  private final io.waterleague.budget.service.BudgetService budget;
  private final SimulationRepository admission;
  private final SiteCatalogRepository sites;
  private final DistrictRepository districts;
  private final LabModelRepository models;
  private final PlacementValidationService validation;
  private final JsonService json;
  private final io.waterleague.disaster.service.DisasterService disasters;

  public HistoricalService(
      HistoricalRepository jobs,
      io.waterleague.budget.service.BudgetService budget,
      SimulationRepository admission,
      SiteCatalogRepository sites,
      DistrictRepository districts,
      LabModelRepository models,
      PlacementValidationService validation,
      JsonService json,
      io.waterleague.disaster.service.DisasterService disasters) {
    this.jobs = jobs;
    this.budget = budget;
    this.admission = admission;
    this.sites = sites;
    this.districts = districts;
    this.models = models;
    this.validation = validation;
    this.json = json;
    this.disasters = disasters;
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
    var district = districts.require(dto.districtId());
    disasters.requireModel(dto.districtId(), dto.modelHash());
    var model = models.require(dto.modelHash());
    if (!model.model().path("mapId").asString().equals(district.mapId()))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var cells = new HashMap<String, PlacementCell>();
    var costs = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    var physical = new ArrayList<Placement>();
    var frozen = new ArrayList<Map<String, Object>>();
    for (var p :
        dto.placements().stream()
            .sorted(Comparator.comparing(HistoricalRequest.Item::cellId))
            .toList()) {
      var c = sites.require(district.id(), p.cellId());
      var types = new HashSet<FacilityType>();
      for (var t : c.allowedTypes()) types.add(FacilityType.valueOf(t));
      cells.put(c.cellId(), new PlacementCell(c.cellId(), types, c.maxAreaM2(), true));
      c.unitCosts().forEach((t, n) -> costs.put(FacilityType.valueOf(t), n));
      physical.add(new Placement(p.cellId(), p.facilityType(), p.areaM2()));
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
                  p.areaM2())));
    }
    validation.validate(physical, cells, costs, budget.limit(), 50);
    String body = json.write(frozen), hash = json.hash(dto.modelHash() + "\n" + body);
    admission.lockAdmission();
    admission.lockOwner(owner);
    var previous = jobs.byKey(owner, dto.requestKey());
    if (previous.isPresent()) {
      if (!previous.get().inputHash().equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
      return view(previous.get());
    }
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
