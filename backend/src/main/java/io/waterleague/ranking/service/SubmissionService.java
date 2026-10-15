package io.waterleague.ranking.service;

import io.waterleague.common.exception.*;
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
  private final ExploratoryResultService results;

  public SubmissionService(
      RankingRepository r,
      SimulationRepository j,
      StrategyRepository s,
      LabModelService m,
      ExploratoryResultService x) {
    rankings = r;
    jobs = j;
    strategies = s;
    model = m;
    results = x;
  }

  @Transactional
  public Object submit(UUID owner, UUID jobId) {
    jobs.lockOwner(owner);
    var job =
        jobs.get(jobId, owner).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    model.requireHash(job.modelHash());
    BigDecimal score = results.score(job);
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
