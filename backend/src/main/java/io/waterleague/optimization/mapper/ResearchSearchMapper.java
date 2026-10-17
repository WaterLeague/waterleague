package io.waterleague.optimization.mapper;

import io.waterleague.common.service.JsonService;
import io.waterleague.optimization.entity.*;
import io.waterleague.optimization.view.SearchView;
import io.waterleague.optimization.view.SearchView.*;
import io.waterleague.ranking.service.ExploratoryResultService;
import io.waterleague.strategy.entity.Placement;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class ResearchSearchMapper {
  private final JsonService json;
  private final ExploratoryResultService scores;

  public ResearchSearchMapper(JsonService json, ExploratoryResultService scores) {
    this.json = json;
    this.scores = scores;
  }

  public SearchView view(
      ResearchSearch r, SearchGeneration generation, List<ResearchCandidate> rows) {
    var candidates =
        rows.stream()
            .map(
                c ->
                    new CandidateView(
                        c.id(),
                        c.arm(),
                        c.ordinal(),
                        List.of(json.read(c.placements(), Placement[].class)),
                        c.modelHash(),
                        c.inputHash(),
                        c.cost(),
                        c.state(),
                        c.result() == null ? null : json.tree(c.result()),
                        c.state().equals("SUCCEEDED")
                            ? scores.score(c.state(), c.modelHash(), c.inputHash(), c.result())
                            : null,
                        c.errorCode(),
                        c.createdAt(),
                        c.finishedAt()))
            .toList();
    List<ArmView> arms = new ArrayList<>();
    for (var arm : SearchArm.values()) {
      var entries = candidates.stream().filter(c -> c.arm() == arm).toList();
      arms.add(
          new ArmView(
              arm,
              entries.size(),
              count(entries, "QUEUED"),
              count(entries, "RUNNING"),
              count(entries, "SUCCEEDED"),
              count(entries, "FAILED"),
              count(entries, "REJECTED"),
              entries.stream()
                  .map(CandidateView::score)
                  .filter(Objects::nonNull)
                  .max(Comparator.naturalOrder())
                  .orElse(null)));
    }
    return new SearchView(
        r.id(),
        r.organizationId(),
        r.requestHash(),
        r.modelHash(),
        r.provenanceHash(),
        r.createdAt(),
        "EXPLORATORY",
        false,
        generation,
        generation.sources().stream()
            .map(s -> s.sample().score())
            .max(Comparator.naturalOrder())
            .orElseThrow(),
        candidates.stream().allMatch(c -> c.state().equals("SUCCEEDED")),
        List.copyOf(arms),
        candidates);
  }

  public Summary summary(SearchView v) {
    return new Summary(
        v.id(),
        v.modelHash(),
        v.generation().settings(),
        v.createdAt(),
        v.sourceBestScore(),
        v.completeComparison(),
        v.arms());
  }

  private int count(List<CandidateView> rows, String state) {
    return (int) rows.stream().filter(c -> c.state().equals(state)).count();
  }
}
