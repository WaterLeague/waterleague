package io.waterleague.historical.service;

import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.cost.service.CostService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.disaster.view.DisasterView;
import io.waterleague.historical.dto.HistoricalDesignRequest;
import io.waterleague.historical.entity.HistoricalDesign;
import io.waterleague.historical.repository.HistoricalDesignRepository;
import io.waterleague.historical.view.HistoricalDesignView;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementValidationService;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

@Service
public class HistoricalDesignService {
  private final HistoricalDesignRepository designs;
  private final SimulationRepository locks;
  private final DisasterService disasters;
  private final SiteCatalogRepository sites;
  private final BudgetService budget;
  private final CostService costs;
  private final PlacementValidationService validation;
  private final JsonService json;

  public HistoricalDesignService(
      HistoricalDesignRepository designs,
      SimulationRepository locks,
      DisasterService disasters,
      SiteCatalogRepository sites,
      BudgetService budget,
      CostService costs,
      PlacementValidationService validation,
      JsonService json) {
    this.designs = designs;
    this.locks = locks;
    this.disasters = disasters;
    this.sites = sites;
    this.budget = budget;
    this.costs = costs;
    this.validation = validation;
    this.json = json;
  }

  private DisasterView.Event event(String id) {
    return disasters.catalog().events().stream()
        .filter(e -> e.id().equals(id))
        .findFirst()
        .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  private JsonNode snapshot(HistoricalDesign value) {
    if (!json.hash(value.snapshotRaw()).equals(value.snapshotSha256()))
      throw new DomainException(ErrorCode.HISTORICAL_DESIGN_INVALID);
    return json.tree(value.snapshotRaw());
  }

  private HistoricalDesignView view(HistoricalDesign value) {
    return new HistoricalDesignView(
        value.eventId(),
        value.revision(),
        value.snapshotSha256(),
        value.createdAt(),
        snapshot(value));
  }

  public HistoricalDesignView get(UUID owner, String event) {
    event(event);
    return designs
        .latest(owner, event)
        .map(this::view)
        .orElse(new HistoricalDesignView(event, 0, null, null, null));
  }

  public HistoricalDesignView revision(UUID owner, String event, long revision) {
    return view(
        designs
            .revision(owner, event, revision)
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND)));
  }

  @Transactional
  public HistoricalDesignView save(UUID owner, String eventId, HistoricalDesignRequest dto) {
    if (dto.placements() == null
        || dto.placements().size() > 50
        || dto.baseRevision() < 0
        || dto.elapsedSeconds() < 0) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var sorted =
        dto.placements().stream()
            .map(
                p ->
                    new HistoricalDesignRequest.Item(
                        p.id(),
                        p.districtId(),
                        p.cellId(),
                        p.facilityType(),
                        p.areaM2().stripTrailingZeros(),
                        p.installedAt()))
            .sorted(
                Comparator.comparing(HistoricalDesignRequest.Item::districtId)
                    .thenComparing(HistoricalDesignRequest.Item::cellId))
            .toList();
    String request =
        json.write(
            new TreeMap<>(
                Map.of(
                    "eventId",
                    eventId,
                    "request",
                    new HistoricalDesignRequest(
                        dto.requestKey(), dto.baseRevision(), dto.elapsedSeconds(), sorted))));
    // 같은 회원의 버전 확인과 추가를 잠금 안에서 수행하여 다른 창의 취소·설치를 덮어쓰지 않는다.
    locks.lockOwner(owner);
    var duplicate = designs.byKey(owner, dto.requestKey());
    if (duplicate.isPresent()) {
      if (!duplicate.get().requestRaw().equals(request))
        throw new DomainException(ErrorCode.HISTORICAL_DESIGN_CONFLICT);
      return view(duplicate.get());
    }
    var previous = designs.latest(owner, eventId);
    if (previous.map(HistoricalDesign::revision).orElse(0L) != dto.baseRevision())
      throw new DomainException(ErrorCode.HISTORICAL_DESIGN_CONFLICT);
    var event = event(eventId);
    var first = event.regions().getFirst();
    if (dto.elapsedSeconds()
        > Duration.between(Instant.parse(first.start()), Instant.parse(first.end())).getSeconds())
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var old = new HashMap<String, JsonNode>();
    if (previous.isPresent())
      for (var row : snapshot(previous.get()).path("placements"))
        old.put(row.path("item").path("id").asString(), row);
    var regions = new HashMap<String, DisasterView.Region>();
    event.regions().forEach(r -> regions.put(r.districtId(), r));
    var frozen = new ArrayList<Object>();
    var allocated = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    var ids = new HashSet<UUID>();
    var locations = new HashSet<String>();
    for (var item : sorted) {
      var region = regions.get(item.districtId());
      if (region == null
          || item.id() == null
          || !ids.add(item.id())
          || !locations.add(item.districtId() + "/" + item.cellId())
          || item.installedAt() == null
          || item.installedAt().getNano() != 0
          || item.installedAt().isBefore(Instant.parse(region.start()))
          || !item.installedAt().isBefore(Instant.parse(region.end())))
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      var same = old.get(item.id().toString());
      if (same != null) {
        if (!same.path("item").equals(json.tree(json.write(item))))
          throw new DomainException(ErrorCode.HISTORICAL_DESIGN_CONFLICT);
        // 변경하지 않은 시설의 공개 형상·참고비·설치 시각은 저장 당시 원문을 유지한다.
        frozen.add(same);
        allocated.merge(item.facilityType(), same.path("cost").decimalValue(), BigDecimal::add);
        continue;
      }
      var site = sites.requireInstallable(item.districtId(), item.cellId());
      var types = new HashSet<FacilityType>();
      site.allowedTypes().forEach(t -> types.add(FacilityType.valueOf(t)));
      var units = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
      site.unitCosts().forEach((t, v) -> units.put(FacilityType.valueOf(t), v));
      var amount =
          validation
              .validate(
                  List.of(new Placement(item.cellId(), item.facilityType(), item.areaM2())),
                  Map.of(
                      item.cellId(),
                      new PlacementCell(
                          item.cellId(), types, site.maxAreaFor(item.facilityType()), true)),
                  units,
                  budget.limit(),
                  1)
              .setScale(2);
      var cost = costs.snapshot(site, item.facilityType(), item.areaM2(), amount);
      frozen.add(
          Map.of(
              "item",
              item,
              "site",
              site,
              "cost",
              amount,
              "costSnapshotRaw",
              cost.raw(),
              "costSnapshotSha256",
              cost.sha256(),
              "rainfallModelHash",
              region.modelHash()));
      allocated.merge(item.facilityType(), amount, BigDecimal::add);
    }
    var accounting = budget.validateDesign(allocated);
    String raw =
        json.write(
            Map.of(
                "schemaVersion",
                1,
                "eventId",
                eventId,
                "elapsedSeconds",
                dto.elapsedSeconds(),
                "placements",
                frozen,
                "budgetPolicy",
                budget.policy(),
                "budgetAccounting",
                accounting,
                "publicAssetPolicy",
                sites.publicAssetPolicy()));
    var value =
        new HistoricalDesign(
            owner,
            eventId,
            dto.baseRevision() + 1,
            dto.requestKey(),
            request,
            raw,
            json.hash(raw),
            Instant.now());
    designs.add(value);
    return view(value);
  }
}
