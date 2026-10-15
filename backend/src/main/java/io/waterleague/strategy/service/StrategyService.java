package io.waterleague.strategy.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.service.LabModelService;
import io.waterleague.strategy.dto.SaveStrategyRequest;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.mapper.StrategyMapper;
import io.waterleague.strategy.repository.StrategyRepository;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StrategyService {
  private final StrategyRepository repo;
  private final StrategyMapper mapper;
  private final LabModelService model;
  private final JsonService json;

  public StrategyService(StrategyRepository r, StrategyMapper m, LabModelService l, JsonService j) {
    repo = r;
    mapper = m;
    model = l;
    json = j;
  }

  public List<Map<String, Object>> list(UUID owner) {
    return repo.list(owner);
  }

  public Map<String, Object> get(UUID id, UUID owner) {
    if (!repo.own(id, owner, false)) missing();
    return Map.of(
        "id",
        id,
        "title",
        repo.title(id),
        "versions",
        repo.versions(id).stream().map(mapper::view).toList());
  }

  @Transactional
  public Map<String, Object> create(UUID owner, SaveStrategyRequest dto) {
    if (dto.baseRevision() != 0) throw new DomainException(ErrorCode.CONFLICT);
    UUID id = UUID.randomUUID();
    repo.create(id, owner, dto.title().strip());
    return save(id, owner, dto);
  }

  @Transactional
  public Map<String, Object> save(UUID id, UUID owner, SaveStrategyRequest dto) {
    if (!repo.own(id, owner, true)) missing();
    model.requireHash(dto.modelHash());
    var history = repo.versions(id);
    if (!history.isEmpty() && !history.getLast().modelHash().equals(dto.modelHash()))
      throw new DomainException(ErrorCode.CONFLICT);
    if (dto.baseRevision() != history.size() || history.size() >= 500)
      throw new DomainException(ErrorCode.CONFLICT);
    var cost = model.validate(dto.modelHash(), dto.placements());
    var placements =
        dto.placements().stream().sorted(Comparator.comparing(Placement::cellId)).toList();
    String body = json.write(placements);
    String before = history.isEmpty() ? "[]" : history.getLast().placements();
    var v =
        new StrategyVersion(
            UUID.randomUUID(),
            id,
            history.size() + 1,
            dto.modelHash(),
            json.hash(dto.modelHash() + "\n" + body),
            body,
            json.write(
                Map.of(
                    "kind",
                    "SERVER_SNAPSHOT_CHANGE",
                    "before",
                    json.tree(before),
                    "after",
                    json.tree(body))),
            dto.designNote(),
            cost,
            "KRW",
            Instant.now());
    repo.rename(id, dto.title().strip());
    repo.add(v);
    return mapper.view(v);
  }

  private void missing() {
    throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }
}
