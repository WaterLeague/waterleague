package io.waterleague.simulation.service;

import io.waterleague.common.exception.*;
import io.waterleague.model.service.LabModelService;
import io.waterleague.simulation.dto.RunRequest;
import io.waterleague.simulation.entity.SimulationJob;
import io.waterleague.simulation.mapper.SimulationMapper;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.repository.StrategyRepository;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SimulationService {
  private final SimulationRepository jobs;
  private final StrategyRepository strategies;
  private final LabModelService model;
  private final SimulationMapper mapper;

  public SimulationService(
      SimulationRepository j, StrategyRepository s, LabModelService m, SimulationMapper v) {
    jobs = j;
    strategies = s;
    model = m;
    mapper = v;
  }

  @Transactional
  public Object enqueue(UUID owner, RunRequest dto) {
    jobs.lockOwner(owner);
    var existing = jobs.byKey(owner, dto.requestKey());
    if (existing.isPresent()) {
      if (!existing.get().versionId().equals(dto.versionId()))
        throw new DomainException(ErrorCode.CONFLICT);
      return mapper.view(existing.get());
    }
    var version =
        strategies
            .version(dto.versionId(), owner)
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    model.requireHash(version.modelHash());
    model.requireRunnable(version.modelHash());
    jobs.lockAdmission();
    if (jobs.active(owner) >= 3 || jobs.totalActive() >= 500)
      throw new DomainException(ErrorCode.RATE_LIMITED);
    var job =
        new SimulationJob(
            UUID.randomUUID(),
            version.id(),
            owner,
            "QUEUED",
            version.modelHash(),
            version.inputHash(),
            null,
            null,
            Instant.now());
    jobs.add(job, dto.requestKey());
    return mapper.view(job);
  }

  public Object get(UUID id, UUID owner) {
    return mapper.view(
        jobs.get(id, owner).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND)));
  }

  public Object list(UUID owner) {
    return jobs.list(owner).stream().map(mapper::view).toList();
  }
}
