package io.waterleague.analysis.mapper;

import io.waterleague.analysis.entity.ResearchComparison;
import io.waterleague.analysis.view.ResearchComparisonView;
import io.waterleague.comparison.view.ComparisonView;
import io.waterleague.simulation.entity.SimulationJob;
import io.waterleague.simulation.mapper.SimulationMapper;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class ResearchAnalysisMapper {
  private final SimulationMapper jobs;

  public ResearchAnalysisMapper(SimulationMapper jobs) {
    this.jobs = jobs;
  }

  public ResearchComparisonView view(ResearchComparison r, SimulationJob source, ComparisonView c) {
    return new ResearchComparisonView(
        r.id(),
        r.organizationId(),
        r.sourceJobId(),
        r.requestHash(),
        r.createdAt(),
        jobs.view(source),
        c);
  }

  public Map<String, Object> summary(ResearchComparison r) {
    return Map.of(
        "id",
        r.id(),
        "sourceJobId",
        r.sourceJobId(),
        "title",
        r.title(),
        "createdAt",
        r.createdAt());
  }
}
