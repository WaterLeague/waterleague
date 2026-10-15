package io.waterleague.comparison.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.comparison.dto.CreateComparisonRequest;
import io.waterleague.comparison.entity.RainfallComparison;
import io.waterleague.comparison.exception.IncompatibleComparisonException;
import io.waterleague.comparison.mapper.ComparisonMapper;
import io.waterleague.comparison.repository.ComparisonRepository;
import io.waterleague.comparison.view.ComparisonView;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.model.service.LabModelService;
import io.waterleague.simulation.dto.RunRequest;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.simulation.service.SimulationService;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.repository.StrategyRepository;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ComparisonService {
  private final ComparisonRepository comparisons;
  private final ComparisonMapper mapper;
  private final StrategyRepository strategies;
  private final SimulationRepository jobs;
  private final SimulationService simulations;
  private final LabModelRepository models;
  private final LabModelService validation;
  private final JsonService json;
  private final ComparisonCompatibilityService compatibility;

  public ComparisonService(
      ComparisonRepository c,
      ComparisonMapper m,
      StrategyRepository s,
      SimulationRepository j,
      SimulationService sim,
      LabModelRepository models,
      LabModelService validation,
      JsonService json,
      ComparisonCompatibilityService compatibility) {
    comparisons = c;
    mapper = m;
    strategies = s;
    jobs = j;
    simulations = sim;
    this.models = models;
    this.validation = validation;
    this.json = json;
    this.compatibility = compatibility;
  }

  public List<Map<String, Object>> list(UUID owner) {
    return comparisons.list(owner).stream().map(mapper::summary).toList();
  }

  public ComparisonView get(UUID id, UUID owner) {
    var c = comparisons.get(id, owner).orElseThrow(ComparisonService::missing);
    var source =
        strategies.version(c.sourceVersionId(), owner).orElseThrow(ComparisonService::missing);
    var values =
        comparisons.jobs(id, owner).stream()
            .map(jobId -> jobs.get(jobId, owner).orElseThrow(ComparisonService::missing))
            .map(
                job ->
                    mapper.job(
                        job,
                        strategies
                            .version(job.versionId(), owner)
                            .orElseThrow(ComparisonService::missing)))
            .toList();
    return mapper.view(c, source, values);
  }

  @Transactional
  public ComparisonView create(UUID owner, CreateComparisonRequest dto) {
    if (dto.modelHashes().size() < 2
        || dto.modelHashes().size() > 3
        || new HashSet<>(dto.modelHashes()).size() != dto.modelHashes().size())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var hashes = dto.modelHashes().stream().sorted().toList();
    String requestHash = json.hash(dto.sourceVersionId() + "\n" + json.write(hashes));
    jobs.lockOwner(owner);
    var previous = comparisons.byKey(owner, dto.requestKey());
    if (previous.isPresent()) {
      if (!previous.get().requestHash().equals(requestHash))
        throw new DomainException(ErrorCode.CONFLICT);
      return get(previous.get().id(), owner);
    }
    var source =
        strategies.version(dto.sourceVersionId(), owner).orElseThrow(ComparisonService::missing);
    var sourceModel = models.require(source.modelHash()).model();
    var placements = List.of(json.read(source.placements(), Placement[].class));
    for (var hash : hashes) {
      var target = models.require(hash).model();
      compatibility.require(sourceModel, target);
      validation.requireRunnable(hash);
      if (validation.validate(hash, placements).compareTo(source.cost()) != 0)
        throw new IncompatibleComparisonException();
    }
    // 기존 큐와 동일한 잠금 순서에서 전체 작업 수를 먼저 확보한다.
    jobs.lockAdmission();
    if (jobs.active(owner) + hashes.size() > 3 || jobs.totalActive() + hashes.size() > 500)
      throw new DomainException(ErrorCode.RATE_LIMITED);
    var c =
        new RainfallComparison(
            UUID.randomUUID(),
            owner,
            source.id(),
            requestHash,
            strategies.title(source.strategyId()),
            Instant.now());
    comparisons.add(c, dto.requestKey());
    int ordinal = 0;
    for (var hash : hashes) {
      UUID strategyId = UUID.randomUUID();
      strategies.create(strategyId, owner, c.title());
      var version =
          new StrategyVersion(
              UUID.randomUUID(),
              strategyId,
              1,
              hash,
              json.hash(hash + "\n" + source.placements()),
              source.placements(),
              json.write(
                  Map.of(
                      "kind",
                      "RAINFALL_COMPARISON_COPY",
                      "comparisonId",
                      c.id(),
                      "sourceVersionId",
                      source.id(),
                      "before",
                      List.of(),
                      "after",
                      placements)),
              source.designNote(),
              source.cost(),
              source.currency(),
              Instant.now());
      strategies.add(version);
      var job = simulations.enqueueJob(owner, new RunRequest(version.id(), UUID.randomUUID()));
      comparisons.link(c.id(), ordinal++, hash, job.id());
    }
    return get(c.id(), owner);
  }

  private static DomainException missing() {
    return new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }
}
