package io.waterleague.ranking.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.service.LabModelService;
import io.waterleague.ranking.repository.RankingRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.repository.StrategyRepository;
import java.math.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SubmissionService {
  private final RankingRepository rankings;
  private final SimulationRepository jobs;
  private final StrategyRepository strategies;
  private final LabModelService model;
  private final JsonService json;

  public SubmissionService(
      RankingRepository r,
      SimulationRepository j,
      StrategyRepository s,
      LabModelService m,
      JsonService x) {
    rankings = r;
    jobs = j;
    strategies = s;
    model = m;
    json = x;
  }

  @Transactional
  public Object submit(UUID owner, UUID jobId) {
    jobs.lockOwner(owner);
    var job =
        jobs.get(jobId, owner).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    model.requireHash(job.modelHash());
    if (!job.state().equals("SUCCEEDED")) throw new DomainException(ErrorCode.CONFLICT);
    var result = json.tree(job.result());
    if (!job.inputHash().equals(result.path("inputHash").asString())
        || !job.modelHash().equals(result.path("modelHash").asString())
        || !"EXPLORATORY".equals(result.path("validationLevel").asString())
        || result.path("official").asBoolean())
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    for (var name : List.of("baseline", "strategy")) {
      var metrics = result.path(name);
      double error = metrics.path("runoffContinuityPercent").asDouble(Double.NaN);
      double volume = metrics.path("accountedDischargeM3").asDouble(Double.NaN);
      if (!Double.isFinite(error) || Math.abs(error) > 1 || !Double.isFinite(volume) || volume < 0)
        throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    }
    BigDecimal base = result.path("baseline").path("accountedDischargeM3").decimalValue();
    BigDecimal strategy = result.path("strategy").path("accountedDischargeM3").decimalValue();
    if (base.compareTo(new BigDecimal("0.000001")) <= 0)
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    BigDecimal score =
        base.subtract(strategy)
            .multiply(BigDecimal.valueOf(100))
            .divide(base, 8, RoundingMode.HALF_UP);
    var version = strategies.version(job.versionId(), owner).orElseThrow();
    if (!rankings.exists(jobId)) rankings.add(jobId, owner, model.hash(), score, version.cost());
    return Map.of("score", score, "official", false, "validationLevel", "EXPLORATORY");
  }

  public Object leaderboard() {
    var rows = rankings.board(model.hash());
    List<Map<String, Object>> ranked = new ArrayList<>();
    BigDecimal previous = null;
    int rank = 0;
    for (int i = 0; i < rows.size(); i++) {
      var row = new LinkedHashMap<>(rows.get(i));
      row.put("currency", "KRW");
      var score = (BigDecimal) row.get("score");
      if (previous == null || score.compareTo(previous) != 0) rank = i + 1;
      row.put("rank", rank);
      ranked.add(row);
      previous = score;
    }
    return Map.of(
        "modelHash", model.hash(), "official", false, "title", "성수 탐색 기록", "entries", ranked);
  }
}
