package io.waterleague.strategy.mapper;

import io.waterleague.common.service.JsonService;
import io.waterleague.strategy.entity.StrategyVersion;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class StrategyMapper {
  private final JsonService json;

  public StrategyMapper(JsonService j) {
    json = j;
  }

  public Map<String, Object> view(StrategyVersion v) {
    var m = new LinkedHashMap<String, Object>();
    m.put("id", v.id());
    m.put("strategyId", v.strategyId());
    m.put("revision", v.revision());
    m.put("modelHash", v.modelHash());
    m.put("inputHash", v.inputHash());
    m.put("placements", json.tree(v.placements()));
    m.put("events", json.tree(v.events()));
    m.put("designNote", v.designNote());
    m.put("cost", v.cost());
    m.put("currency", v.currency());
    m.put("createdAt", v.createdAt());
    return m;
  }
}
