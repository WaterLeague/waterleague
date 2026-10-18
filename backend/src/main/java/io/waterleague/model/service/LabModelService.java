package io.waterleague.model.service;

import io.waterleague.common.exception.*;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementValidationService;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class LabModelService {
  private final LabModelRepository models;
  private final PlacementValidationService placements;

  public LabModelService(LabModelRepository m, PlacementValidationService p) {
    models = m;
    placements = p;
  }

  public String hash() {
    return models.hash();
  }

  public void requireHash(String hash) {
    models.require(hash);
  }

  public void requireRunnable(String hash) {
    if (!models.require(hash).model().path("simulationAvailable").asBoolean())
      throw new DomainException(ErrorCode.MODEL_NOT_ELIGIBLE);
  }

  public Map<String, Object> view() {
    return view(hash());
  }

  public Map<String, Object> view(String hash) {
    var item = models.require(hash);
    return Map.of("modelHash", item.hash(), "model", item.model());
  }

  public boolean contains(String hash) {
    return models.contains(hash);
  }

  public Object catalog() {
    return Map.of(
        "defaultModelHash",
        hash(),
        "models",
        models.all().stream()
            .map(
                item ->
                    Map.of(
                        "modelHash",
                        item.hash(),
                        "title",
                        item.model().path("title").asString(),
                        "mapId",
                        item.model().path("mapId").asString("seongsu-candidate-01"),
                        "mapTitle",
                        item.model().path("mapTitle").asString("OSM 초기 지도"),
                        "regionalRainfallUse",
                        item.model().path("regionalRainfallUse").asString("OBSERVED_REPLAY"),
                        "rainfall",
                        ((tools.jackson.databind.node.ObjectNode)
                                item.model().path("rainfall").deepCopy())
                            .without("depthsMm"),
                        "budget",
                        item.model().path("budget").longValue(),
                        "validationLevel",
                        "EXPLORATORY",
                        "official",
                        false))
            .toList());
  }

  public BigDecimal validate(String hash, List<Placement> values) {
    var model = models.require(hash).model();
    Map<String, PlacementCell> cells = new HashMap<>();
    for (var c : model.path("cells")) {
      Set<FacilityType> types = new HashSet<>();
      for (var t : c.path("allowedTypes")) types.add(FacilityType.valueOf(t.asString()));
      cells.put(
          c.path("id").asString(),
          new PlacementCell(
              c.path("id").asString(), types, c.path("maxAreaM2").decimalValue(), true));
    }
    Map<FacilityType, BigDecimal> costs = new EnumMap<>(FacilityType.class);
    for (var t : FacilityType.values())
      if (model.path("unitCosts").has(t.name()))
        costs.put(t, model.path("unitCosts").path(t.name()).decimalValue());
    return placements.validate(
        values,
        cells,
        costs,
        model.path("budget").decimalValue(),
        model.path("maxPlacements").asInt());
  }
}
