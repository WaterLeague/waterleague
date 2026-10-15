package io.waterleague.simulation.mapper;

import io.waterleague.common.service.JsonService;
import io.waterleague.simulation.entity.SimulationJob;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class SimulationMapper {
  private final JsonService json;

  public SimulationMapper(JsonService j) {
    json = j;
  }

  public Map<String, Object> view(SimulationJob j) {
    var m = new LinkedHashMap<String, Object>();
    m.put("id", j.id());
    m.put("versionId", j.versionId());
    m.put("state", j.state());
    m.put("modelHash", j.modelHash());
    m.put("inputHash", j.inputHash());
    m.put("result", j.result() == null ? null : json.tree(j.result()));
    m.put("errorCode", j.errorCode());
    m.put("createdAt", j.createdAt());
    return m;
  }
}
