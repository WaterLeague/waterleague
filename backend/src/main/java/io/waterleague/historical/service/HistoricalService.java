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
  private final io.waterleague.historical.repository.HistoricalDesignRepository designs;

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
      io.waterleague.cost.service.CostService costRecords,
      io.waterleague.historical.repository.HistoricalDesignRepository designs) {
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
    this.designs = designs;
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

  public List<HistoricalView> guestList(String guest) {
    return jobs.guestList(guest).stream().map(this::view).toList();
  }

  public HistoricalView guestGet(String guest, UUID id) {
    return view(
        jobs.guestGet(guest, id)
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND)));
  }

  @Transactional
  public HistoricalView createGuest(
      String guest, io.waterleague.historical.dto.GuestHistoricalRequest dto) {
    var event =
        disasters.catalog().events().stream()
            .filter(e -> e.id().equals(dto.eventId()))
            .findFirst()
            .orElseThrow(() -> new DomainException(ErrorCode.PLACEMENT_INVALID));
    var sorted =
        dto.placements().stream()
            .sorted(
                Comparator.comparing(
                        io.waterleague.historical.dto.GuestHistoricalRequest.Item::districtId)
                    .thenComparing(i -> i.placement().cellId()))
            .toList();
    var allocated = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    var locations = new HashSet<String>();
    for (var entry : sorted) {
      var p = entry.placement();
      var region =
          event.regions().stream()
              .filter(r -> r.districtId().equals(entry.districtId()))
              .findFirst()
              .orElseThrow(() -> new DomainException(ErrorCode.PLACEMENT_INVALID));
      if (!locations.add(entry.districtId() + "/" + p.cellId())
          || p.installedAt() == null
          || p.installedAt().getNano() != 0
          || p.installedAt().isBefore(Instant.parse(region.start()))
          || !p.installedAt().isBefore(Instant.parse(region.end())))
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      var site = sites.requireInstallable(entry.districtId(), p.cellId());
      if (!site.modelHash().equals(p.siteModelHash()))
        throw new DomainException(ErrorCode.HISTORICAL_SITE_CHANGED);
      var types = new HashSet<FacilityType>();
      site.allowedTypes().forEach(t -> types.add(FacilityType.valueOf(t)));
      var units = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
      site.unitCosts().forEach((t, v) -> units.put(FacilityType.valueOf(t), v));
      var cost =
          validation.validate(
              List.of(new Placement(p.cellId(), p.facilityType(), p.areaM2())),
              Map.of(
                  p.cellId(),
                  new PlacementCell(p.cellId(), types, site.maxAreaFor(p.facilityType()), true)),
              units,
              budget.limit(),
              1);
      allocated.merge(p.facilityType(), cost, BigDecimal::add);
    }
    // 비회원도 다른 구에 예산을 복제하지 않도록 전체 설계를 함께 검증한다.
    var accounting = budget.validateDesign(allocated);
    var region =
        event.regions().stream()
            .filter(r -> r.districtId().equals(dto.districtId()))
            .findFirst()
            .orElseThrow(() -> new DomainException(ErrorCode.PLACEMENT_INVALID));
    var selected =
        sorted.stream()
            .filter(i -> i.districtId().equals(dto.districtId()))
            .map(io.waterleague.historical.dto.GuestHistoricalRequest.Item::placement)
            .toList();
    if (selected.isEmpty()) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var request =
        new HistoricalRequest(
            dto.requestKey(),
            dto.districtId(),
            region.modelHash(),
            selected,
            null,
            "INSTALLATION_TIME_EXPERIMENT_V1",
            null);
    var snapshot =
        json.write(
            Map.of("eventId", dto.eventId(), "placements", sorted, "budgetAccounting", accounting));
    return createInternal(null, request, guest, snapshot);
  }

  @Transactional
  public HistoricalView create(UUID owner, HistoricalRequest dto) {
    return createInternal(owner, dto, null, null);
  }

  private HistoricalView createInternal(
      UUID owner, HistoricalRequest dto, String guest, String guestSnapshot) {
    boolean savedDesign = dto.designRevision() != null;
    if (savedDesign != (dto.eventId() != null) || (savedDesign && dto.temporalPolicy() == null))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
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
    // 편집 저장과 계산 승인 사이의 버전 확인을 같은 회원 잠금으로 직렬화한다.
    admission.lockAdmission();
    if (guest == null)
      try {
        admission.lockOwner(owner);
      } catch (org.springframework.dao.EmptyResultDataAccessException e) {
        throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
      }
    var previous =
        guest == null
            ? jobs.byKey(owner, dto.requestKey())
            : jobs.guestByKey(guest, dto.requestKey());
    if (previous.isPresent()) {
      // 원장 추가 전 입력도 같은 사용자 요청이면 기존 실행을 반환한다.
      var old = previous.get();
      var oldPlacements = json.tree(old.placements());
      if (guest != null
          && !Objects.equals(
              oldPlacements.get(0).path("guestDesignSnapshotRaw").asString(), guestSnapshot))
        throw new DomainException(ErrorCode.CONFLICT);
      if (!Objects.equals(
              oldPlacements.get(0).has("designRevision")
                  ? oldPlacements.get(0).path("designRevision").longValue()
                  : null,
              dto.designRevision())
          || !Objects.equals(
              oldPlacements.get(0).has("designEventId")
                  ? oldPlacements.get(0).path("designEventId").asString()
                  : null,
              dto.eventId())) throw new DomainException(ErrorCode.CONFLICT);
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
    var savedRows = new HashMap<String, tools.jackson.databind.JsonNode>();
    if (savedDesign) {
      var saved =
          designs
              .latest(owner, dto.eventId())
              .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
      if (saved.revision() != dto.designRevision())
        throw new DomainException(ErrorCode.HISTORICAL_DESIGN_CONFLICT);
      if (!json.hash(saved.snapshotRaw()).equals(saved.snapshotSha256()))
        throw new DomainException(ErrorCode.HISTORICAL_DESIGN_INVALID);
      var whole = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
      for (var row : json.tree(saved.snapshotRaw()).path("placements")) {
        var item = row.path("item");
        whole.merge(
            FacilityType.valueOf(item.path("facilityType").asString()),
            row.path("cost").decimalValue(),
            BigDecimal::add);
        if (item.path("districtId").asString().equals(dto.districtId())) {
          if (!row.path("rainfallModelHash").asString().equals(dto.modelHash()))
            throw new DomainException(ErrorCode.PLACEMENT_INVALID);
          savedRows.put(item.path("cellId").asString(), row);
        }
      }
      // 다른 구의 계산을 순차 실행해도 설계 전체에 한 번 부여한 예산을 나눠 중복 사용하지 않는다.
      var wholeAccounting = budget.validateDesign(whole);
      if (savedRows.size() != dto.placements().size())
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      for (var p : dto.placements()) {
        var row = savedRows.get(p.cellId());
        if (row == null
            || !row.path("item").path("facilityType").asString().equals(p.facilityType().name())
            || row.path("item").path("areaM2").decimalValue().compareTo(p.areaM2()) != 0
            || !Instant.parse(row.path("item").path("installedAt").asString())
                .equals(p.installedAt())
            || !row.path("site").path("modelHash").asString().equals(p.siteModelHash()))
          throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      }
      frozen.getFirst().put("designRevision", saved.revision());
      frozen.getFirst().put("designEventId", dto.eventId());
      frozen.getFirst().put("designSnapshotRaw", saved.snapshotRaw());
      frozen.getFirst().put("designSnapshotSha256", saved.snapshotSha256());
      frozen.getFirst().put("wholeDesignBudgetAccounting", wholeAccounting);
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
      var savedRow = savedRows.get(row.get("cellId"));
      if (savedRow != null) {
        if (savedRow
                .path("cost")
                .decimalValue()
                .compareTo(site.unitCosts().get(type.name()).multiply(area))
            != 0) throw new DomainException(ErrorCode.HISTORICAL_SITE_CHANGED);
        row.put("costSnapshotRaw", savedRow.path("costSnapshotRaw").asString());
        row.put("costSnapshotSha256", savedRow.path("costSnapshotSha256").asString());
      } else {
        row.put("costSnapshotRaw", record.raw());
        row.put("costSnapshotSha256", record.sha256());
      }
    }
    if (guest != null) {
      frozen.getFirst().put("guestDesignSnapshotRaw", guestSnapshot);
      frozen.getFirst().put("guestDesignSnapshotSha256", json.hash(guestSnapshot));
    }
    body = json.write(frozen);
    hash = json.hash(dto.modelHash() + "\n" + body);
    if ((guest == null ? jobs.active(owner) : jobs.guestActive(guest)) >= 2
        || admission.totalActive() >= 20)
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
    if (guest == null) jobs.add(j, dto.requestKey());
    else jobs.addGuest(j, dto.requestKey(), guest);
    return view(j);
  }
}
