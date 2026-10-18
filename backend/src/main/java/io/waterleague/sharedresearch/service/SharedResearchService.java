package io.waterleague.sharedresearch.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.sharedresearch.entity.SharedResearchJob;
import io.waterleague.sharedresearch.repository.SharedResearchRepository;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SharedResearchService {
  private final SharedResearchRepository records;
  private final SharedResearchArtifactService artifacts;
  private final ResearchRepository research;
  private final AccountRepository accounts;

  public SharedResearchService(
      SharedResearchRepository records,
      SharedResearchArtifactService artifacts,
      ResearchRepository research,
      AccountRepository accounts) {
    this.records = records;
    this.artifacts = artifacts;
    this.research = research;
    this.accounts = accounts;
  }

  private Account member(UUID actor) {
    var a = accounts.byId(actor).orElseThrow(() -> new DomainException(ErrorCode.ACCESS_DENIED));
    if (!a.usable() || !a.role().equals("MEMBER"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    return a;
  }

  private Account organization(UUID actor) {
    var a = member(actor);
    if (!a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    return a;
  }

  public Object consents(UUID actor) {
    member(actor);
    return records.consents(actor);
  }

  @Transactional
  public void consent(UUID actor, UUID org, boolean granted) {
    research.ownerLock(actor);
    member(actor);
    if (!research.approved(org)) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    records.consent(actor, org, granted);
    research.audit(actor, granted ? "SHARED_CONSENT_GRANTED" : "SHARED_CONSENT_REVOKED", org);
  }

  private LocalDate week(LocalDate value) {
    var current =
        LocalDate.now(ZoneId.of("Asia/Seoul"))
            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    if (value == null) return current;
    if (value.getDayOfWeek() != DayOfWeek.MONDAY || value.isAfter(current))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    return value;
  }

  public Object list(UUID actor, boolean institution, LocalDate start) {
    var a = institution ? organization(actor) : member(actor);
    var week = week(start);
    var rows = records.list(actor, institution ? a.organizationId() : null, week);
    if (institution) {
      var fresh = organization(actor);
      if (!Objects.equals(fresh.organizationId(), a.organizationId()))
        throw new DomainException(ErrorCode.ACCESS_DENIED);
      // 조회 도중 동의가 철회된 행도 응답에 포함하지 않는다.
      rows = records.list(actor, fresh.organizationId(), week);
    } else member(actor);
    return Map.of(
        "weekStart",
        week,
        "scope",
        institution ? "CONSENTED_ORGANIZATION" : "OWNER",
        "entries",
        rows);
  }

  private SharedResearchJob authorize(UUID actor, boolean institution, UUID id) {
    var a = institution ? organization(actor) : member(actor);
    var job = records.find(id).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (institution
        ? !records.allowed(job.ownerId(), a.organizationId())
        : !job.ownerId().equals(actor)) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return job;
  }

  public SharedResearchJob surfaceAccess(UUID actor, boolean institution, UUID id) {
    return authorize(actor, institution, id);
  }

  private Map<String, Object> installation(SharedResearchJob j) {
    var value = new LinkedHashMap<String, Object>();
    value.put("id", j.installationId());
    value.put("districtId", j.districtId());
    value.put("cellId", j.cellId());
    value.put("playerName", j.playerName());
    value.put("facilityType", j.facilityType());
    value.put("areaM2", j.areaM2());
    value.put("costKrw", j.costKrw());
    value.put("installedAt", j.installedAt());
    value.put("removedAt", j.removedAt());
    return value;
  }

  public Object detail(UUID actor, boolean institution, UUID id) {
    var job = authorize(actor, institution, id);
    var data = new LinkedHashMap<>(artifacts.detail(job));
    authorize(actor, institution, id);
    research.audit(actor, "SHARED_RESEARCH_READ", id);
    data.put("jobId", id);
    data.put("installation", installation(job));
    return data;
  }

  public byte[] bundle(UUID actor, boolean institution, UUID id) {
    var job = authorize(actor, institution, id);
    var scope = new LinkedHashMap<String, Object>();
    scope.put("purpose", "EXPLORATORY_RESEARCH_ONLY");
    scope.put("exportedAt", Instant.now());
    scope.put("installation", installation(job));
    scope.put("inputHash", job.inputHash());
    scope.put("manifestSha256", job.manifestHash());
    scope.put("notice", "선택 표면의 가정 기반 계산. 실제 침수·시공 효과나 사업 활용 승인 아님. 동의 철회는 이후 접근에 적용.");
    var bytes = artifacts.bundle(job, scope);
    authorize(actor, institution, id);
    research.audit(actor, "SHARED_RESEARCH_EXPORT", id);
    return bytes;
  }
}
