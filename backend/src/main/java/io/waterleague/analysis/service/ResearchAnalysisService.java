package io.waterleague.analysis.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.analysis.dto.*;
import io.waterleague.analysis.entity.*;
import io.waterleague.analysis.exception.IncompatibleAnalysisException;
import io.waterleague.analysis.mapper.ResearchAnalysisMapper;
import io.waterleague.analysis.repository.ResearchAnalysisRepository;
import io.waterleague.analysis.view.*;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.comparison.dto.CreateComparisonRequest;
import io.waterleague.comparison.service.ComparisonService;
import io.waterleague.model.service.LabModelService;
import io.waterleague.ranking.service.ExploratoryResultService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.research.service.ResearchService;
import io.waterleague.simulation.entity.SimulationJob;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.repository.StrategyRepository;
import java.io.IOException;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ResearchAnalysisService {
  private final ResearchAnalysisRepository analyses;
  private final ResearchAnalysisMapper mapper;
  private final ResearchRepository research;
  private final ResearchService exports;
  private final ComparisonService comparisons;
  private final SimulationRepository jobs;
  private final StrategyRepository strategies;
  private final AccountRepository accounts;
  private final LabModelService models;
  private final ExploratoryResultService scores;
  private final PatternAnalysisService patterns;
  private final JsonService json;

  public ResearchAnalysisService(
      ResearchAnalysisRepository a,
      ResearchAnalysisMapper m,
      ResearchRepository r,
      ResearchService exports,
      ComparisonService c,
      SimulationRepository j,
      StrategyRepository s,
      AccountRepository accounts,
      LabModelService models,
      ExploratoryResultService scores,
      PatternAnalysisService patterns,
      JsonService json) {
    analyses = a;
    mapper = m;
    research = r;
    this.exports = exports;
    comparisons = c;
    jobs = j;
    strategies = s;
    this.accounts = accounts;
    this.models = models;
    this.scores = scores;
    this.patterns = patterns;
    this.json = json;
  }

  private Account organization(Account actor) {
    var a = accounts.byId(actor.id()).orElseThrow(ResearchAnalysisService::missing);
    if (!a.usable()
        || !a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    return a;
  }

  private void allowed(Account a, UUID source) {
    var current = organization(a);
    if (!Objects.equals(current.organizationId(), a.organizationId())
        || !research.allowed(source, current.organizationId())) throw missing();
  }

  private SimulationJob source(Account a, UUID id) {
    allowed(a, id);
    var job = jobs.get(id).orElseThrow(ResearchAnalysisService::missing);
    scores.score(job);
    return job;
  }

  private StrategyVersion version(SimulationJob job) {
    var v =
        strategies
            .version(job.versionId(), job.ownerId())
            .orElseThrow(ResearchAnalysisService::missing);
    if (!v.inputHash().equals(job.inputHash())
        || !v.modelHash().equals(job.modelHash())
        || !json.hash(v.modelHash() + "\n" + v.placements()).equals(v.inputHash()))
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    var placements = List.of(json.read(v.placements(), Placement[].class));
    if (models.validate(v.modelHash(), placements).compareTo(v.cost()) != 0)
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    return v;
  }

  private ResearchComparison require(Account a, UUID id) {
    var current = organization(a);
    var r =
        analyses.get(id, current.organizationId()).orElseThrow(ResearchAnalysisService::missing);
    allowed(current, r.sourceJobId());
    return r;
  }

  public List<Map<String, Object>> list(Account actor) {
    var a = organization(actor);
    var rows =
        analyses.list(a.organizationId()).stream()
            .filter(r -> research.allowed(r.sourceJobId(), a.organizationId()))
            .toList();
    for (var r : rows) allowed(a, r.sourceJobId());
    if (!organization(a).organizationId().equals(a.organizationId())) throw missing();
    return rows.stream().map(mapper::summary).toList();
  }

  public ResearchComparisonView get(Account actor, UUID id) {
    var a = organization(actor);
    var r = require(a, id);
    var source = source(a, r.sourceJobId());
    var result = mapper.view(r, source, comparisons.get(r.comparisonId(), source.ownerId()));
    allowed(a, r.sourceJobId());
    research.audit(a.id(), "RESEARCH_COMPARISON_READ", r.id());
    return result;
  }

  @Transactional
  public ResearchComparisonView create(Account actor, CreateResearchComparisonRequest dto) {
    var a = organization(actor);
    if (dto.modelHashes().size() < 2
        || dto.modelHashes().size() > 3
        || new HashSet<>(dto.modelHashes()).size() != dto.modelHashes().size())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var source = source(a, dto.sourceJobId());
    jobs.lockOwner(source.ownerId());
    allowed(a, source.id());
    var v = version(source);
    var hashes = dto.modelHashes().stream().sorted().toList();
    String hash =
        json.hash(json.write(List.of("RESEARCH_RAINFALL_COMPARISON_V1", source.id(), hashes)));
    // 기존 개인 계산과 같은 잠금 순서로 기관 멱등키와 큐 한도를 함께 직렬화한다.
    jobs.lockAdmission();
    var old = analyses.byKey(a.organizationId(), dto.requestKey());
    if (old.isPresent()) {
      if (!old.get().requestHash().equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
      return get(a, old.get().id());
    }
    if (analyses.active(a.organizationId()) + hashes.size() > 9)
      throw new DomainException(ErrorCode.RATE_LIMITED);
    UUID id = UUID.randomUUID();
    var c =
        comparisons.createForResearch(
            source.ownerId(),
            new CreateComparisonRequest(v.id(), hashes, UUID.randomUUID()),
            a.organizationId(),
            id,
            source.id());
    var r =
        new ResearchComparison(
            id,
            a.organizationId(),
            a.id(),
            source.id(),
            c.id(),
            dto.requestKey(),
            hash,
            c.title(),
            Instant.now());
    analyses.add(r);
    allowed(a, source.id());
    research.audit(a.id(), "RESEARCH_COMPARISON_CREATED", id);
    return mapper.view(r, source, c);
  }

  public byte[] bundle(Account actor, UUID id, UUID jobId) throws IOException {
    var a = organization(actor);
    var r = require(a, id);
    var source = source(a, r.sourceJobId());
    if (!analyses.contains(r.comparisonId(), jobId)) throw missing();
    var target = jobs.get(jobId, source.ownerId()).orElseThrow(ResearchAnalysisService::missing);
    return exports.comparisonBundle(
        a,
        jobId,
        id,
        Map.of(
            "purpose",
            "RESEARCH_RAINFALL_COMPARISON",
            "organizationId",
            a.organizationId(),
            "researchComparisonId",
            id,
            "sourceJobId",
            source.id(),
            "sourceVersionId",
            source.versionId(),
            "sourceModelHash",
            source.modelHash(),
            "targetModelHash",
            target.modelHash(),
            "requestHash",
            r.requestHash()),
        () -> {
          require(a, id);
          if (!analyses.contains(r.comparisonId(), jobId)) throw missing();
        });
  }

  public PatternAnalysisView patterns(Account actor, PatternAnalysisRequest dto) {
    var a = organization(actor);
    if (new HashSet<>(dto.jobIds()).size() != dto.jobIds().size())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    List<PatternSample> samples = new ArrayList<>();
    String hash = null;
    for (UUID id : dto.jobIds()) {
      var job = source(a, id);
      var v = version(job);
      if (hash != null && !hash.equals(v.modelHash())) throw new IncompatibleAnalysisException();
      hash = v.modelHash();
      samples.add(
          new PatternSample(
              id,
              v.inputHash(),
              scores.score(job),
              v.cost(),
              List.of(json.read(v.placements(), Placement[].class))));
    }
    var result = patterns.analyze(hash, samples, dto.topK());
    for (UUID id : dto.jobIds()) allowed(a, id);
    research.audit(a.id(), "RESEARCH_PATTERN_READ", null);
    return result;
  }

  private static DomainException missing() {
    return new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }
}
