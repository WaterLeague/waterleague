package io.waterleague.research.service;

import io.waterleague.account.entity.Account;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.service.LabModelService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.simulation.mapper.SimulationMapper;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.mapper.StrategyMapper;
import io.waterleague.strategy.repository.StrategyRepository;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ResearchService {
  private final ResearchRepository research;
  private final SimulationRepository jobs;
  private final StrategyRepository strategies;
  private final StrategyMapper versions;
  private final SimulationMapper mapper;
  private final LabModelService model;
  private final JsonService json;
  private final Path artifacts;
  private final io.waterleague.utilization.service.UtilizationService utilization;

  public ResearchService(
      ResearchRepository r,
      SimulationRepository j,
      StrategyRepository s,
      StrategyMapper v,
      SimulationMapper m,
      LabModelService l,
      JsonService x,
      io.waterleague.utilization.service.UtilizationService utilization,
      @Value("${waterleague.artifacts}") String path) {
    research = r;
    jobs = j;
    strategies = s;
    versions = v;
    mapper = m;
    model = l;
    json = x;
    this.utilization = utilization;
    artifacts = Path.of(path).toAbsolutePath().normalize();
  }

  public Object organizations() {
    return research.organizations();
  }

  public Object consents(Account a) {
    return research.consents(a.id());
  }

  @Transactional
  public void consent(Account a, UUID org, boolean value) {
    research.ownerLock(a.id());
    if (!research.approved(org)) missing();
    research.consent(a.id(), org, value);
    research.audit(a.id(), value ? "CONSENT_GRANTED" : "CONSENT_REVOKED", org);
  }

  private void organization(Account a) {
    if (!a.usable()
        || !a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  public Object list(Account a, String hash) {
    organization(a);
    model.requireHash(hash == null ? model.hash() : hash);
    return research.list(a.organizationId(), hash == null ? model.hash() : hash);
  }

  public Object detail(Account a, UUID id) {
    authorize(a, id);
    research.audit(a.id(), "RESEARCH_READ", id);
    return detailData(a, id);
  }

  private Object detailData(Account a, UUID id) {
    var job = jobs.get(id).orElseThrow();
    var version = strategies.version(job.versionId(), job.ownerId()).orElseThrow();
    return Map.of(
        "leagueContexts",
        research.leagueContexts(id, a.id(), a.organizationId()),
        "lab",
        snapshot(job),
        "simulation",
        mapper.view(job),
        "version",
        versions.view(version),
        "history",
        strategies.versions(version.strategyId()).stream()
            .filter(v -> v.revision() <= version.revision())
            .map(versions::view)
            .toList());
  }

  private Object snapshot(io.waterleague.simulation.entity.SimulationJob job) {
    if (model.contains(job.modelHash())) return model.view(job.modelHash());
    var token = UUID.fromString(json.tree(job.result()).path("artifactToken").asString());
    Path source =
        artifacts
            .resolve(job.id().toString())
            .resolve(token.toString())
            .resolve("model-source.json");
    try {
      if (!Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)
          || Files.size(source) > 2 * 1024 * 1024) missing();
      String content = Files.readString(source);
      if (!json.hash(content).equals(job.modelHash()))
        throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
      return Map.of("modelHash", job.modelHash(), "model", json.tree(content));
    } catch (IOException e) {
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    }
  }

  private void authorize(Account a, UUID id) {
    organization(a);
    if (!research.allowed(id, a.organizationId())) missing();
  }

  public byte[] bundle(Account a, UUID id, boolean institution) throws IOException {
    Runnable authorization =
        () -> {
          if (institution) authorize(a, id);
          else if (jobs.get(id, a.id()).isEmpty()) missing();
        };
    authorization.run();
    return buildBundle(
        a,
        id,
        Map.of(
            "purpose",
            "EXPLORATORY_ONLY",
            "organizationId",
            institution ? a.organizationId().toString() : "OWNER"),
        authorization,
        "RESEARCH_EXPORT",
        id);
  }

  public byte[] applicationBundle(Account a, UUID requestId) throws IOException {
    var grant = utilization.grant(a, requestId);
    return buildBundle(
        a,
        grant.jobId(),
        utilization.exportScope(grant),
        () -> utilization.requireSameGrant(a, grant),
        "APPLICATION_EXPORT",
        requestId);
  }

  private byte[] buildBundle(
      Account a,
      UUID id,
      Map<String, Object> scope,
      Runnable authorization,
      String auditAction,
      UUID auditObject)
      throws IOException {
    authorization.run();
    var job = jobs.get(id).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!job.state().equals("SUCCEEDED")) throw new DomainException(ErrorCode.CONFLICT);
    var token = UUID.fromString(json.tree(job.result()).path("artifactToken").asString());
    Path dir = artifacts.resolve(id.toString()).resolve(token.toString());
    var bytes = new ByteArrayOutputStream();
    long total = 0;
    try (var zip = new ZipOutputStream(bytes)) {
      for (String name :
          List.of(
              "manifest.json",
              "builder.py",
              "model-source.json",
              "model.json",
              "placements.json",
              "request.json",
              "result.json",
              "baseline.inp",
              "baseline.rpt",
              "baseline.out",
              "strategy.inp",
              "strategy.rpt",
              "strategy.out",
              "low.inp",
              "low.rpt",
              "low.out",
              "high.inp",
              "high.rpt",
              "high.out")) {
        Path file = dir.resolve(name);
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS))
          throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
        total += Files.size(file);
        if (total > 64 * 1024 * 1024) throw new DomainException(ErrorCode.CONFLICT);
        zip.putNextEntry(new ZipEntry(name));
        Files.copy(file, zip);
        zip.closeEntry();
      }
      zip.putNextEntry(new ZipEntry("strategy-history.json"));
      zip.write(json.write(detailData(a, id)).getBytes(java.nio.charset.StandardCharsets.UTF_8));
      zip.closeEntry();
      zip.putNextEntry(new ZipEntry("access-scope.json"));
      var exportScope = new LinkedHashMap<String, Object>(scope);
      exportScope.put("exportedAt", java.time.Instant.now().toString());
      exportScope.put("notice", "현장 검증 전 가정 기반 결과. 동의 철회는 이후 접근에 적용. 실제 시공·안전 승인 아님.");
      zip.write(json.write(exportScope).getBytes(java.nio.charset.StandardCharsets.UTF_8));
      zip.closeEntry();
    }
    authorization.run();
    research.audit(a.id(), auditAction, auditObject);
    return bytes.toByteArray();
  }

  private void missing() {
    throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }
}
