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
    if (!hash().equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
  }

  public void requireRunnable() {
    if (!models.model().path("simulationAvailable").asBoolean())
      throw new DomainException(ErrorCode.MODEL_NOT_ELIGIBLE);
  }

  public Map<String, Object> view() {
    return Map.of("modelHash", hash(), "model", models.model());
  }

  public BigDecimal validate(List<Placement> values) {
    Map<String, PlacementCell> cells = new HashMap<>();
    for (var c : models.model().path("cells")) {
      Set<FacilityType> types = new HashSet<>();
      for (var t : c.path("allowedTypes")) types.add(FacilityType.valueOf(t.asString()));
      cells.put(
          c.path("id").asString(),
          new PlacementCell(
              c.path("id").asString(), types, c.path("maxAreaM2").decimalValue(), true));
    }
    Map<FacilityType, BigDecimal> costs = new EnumMap<>(FacilityType.class);
    for (var t : FacilityType.values())
      costs.put(t, models.model().path("unitCosts").path(t.name()).decimalValue());
    return placements.validate(
        values,
        cells,
        costs,
        models.model().path("budget").decimalValue(),
        models.model().path("maxPlacements").asInt());
  }
}
