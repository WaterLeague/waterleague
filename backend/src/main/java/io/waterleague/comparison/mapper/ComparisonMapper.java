package io.waterleague.comparison.mapper;

import io.waterleague.comparison.entity.RainfallComparison;
import io.waterleague.comparison.view.ComparisonView;
import io.waterleague.simulation.entity.SimulationJob;
import io.waterleague.simulation.mapper.SimulationMapper;
import io.waterleague.strategy.entity.StrategyVersion;
import io.waterleague.strategy.mapper.StrategyMapper;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class ComparisonMapper {
  private final StrategyMapper versions;
  private final SimulationMapper jobs;

  public ComparisonMapper(StrategyMapper v, SimulationMapper j) {
    versions = v;
    jobs = j;
  }

  public ComparisonView view(
      RainfallComparison c, StrategyVersion source, List<Map<String, Object>> values) {
    return new ComparisonView(
        c.id(), c.title(), c.sourceVersionId(), c.createdAt(), versions.view(source), values);
  }

  public Map<String, Object> job(SimulationJob job, StrategyVersion version) {
    var view = new LinkedHashMap<>(jobs.view(job));
    view.put("strategyId", version.strategyId());
    return view;
  }

  public Map<String, Object> summary(RainfallComparison c) {
    return Map.of(
        "id",
        c.id(),
        "title",
        c.title(),
        "sourceVersionId",
        c.sourceVersionId(),
        "createdAt",
        c.createdAt());
  }
}
