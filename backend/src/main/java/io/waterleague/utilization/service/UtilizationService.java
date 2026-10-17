package io.waterleague.utilization.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.utilization.dto.*;
import io.waterleague.utilization.entity.*;
import io.waterleague.utilization.exception.UtilizationConflictException;
import io.waterleague.utilization.mapper.UtilizationMapper;
import io.waterleague.utilization.repository.UtilizationRepository;
import io.waterleague.utilization.view.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UtilizationService {
  public static final String POLICY = "APPLICATION_REVIEW_2026_10_V1";
  private final UtilizationRepository requests;
  private final UtilizationMapper mapper;
  private final ResearchRepository research;
  private final SimulationRepository jobs;
  private final AccountRepository accounts;
  private final JsonService json;

  public UtilizationService(
      UtilizationRepository requests,
      UtilizationMapper mapper,
      ResearchRepository research,
      SimulationRepository jobs,
      AccountRepository accounts,
      JsonService json) {
    this.requests = requests;
    this.mapper = mapper;
    this.research = research;
    this.jobs = jobs;
    this.accounts = accounts;
    this.json = json;
  }

  private void member(Account a) {
    if (!a.usable() || !a.role().equals("MEMBER"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  private void organization(Account a) {
    member(a);
    if (!a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  private void researchAccess(Account a, UUID job) {
    organization(a);
    if (!research.allowed(job, a.organizationId())) throw missing();
  }

  private UtilizationRequest participant(Account a, UUID id) {
    member(a);
    var r = requests.get(id).orElseThrow(UtilizationService::missing);
    if (!r.ownerId().equals(a.id())) {
      if (!a.organizationMember() || !r.organizationId().equals(a.organizationId()))
        throw missing();
      organization(a);
    }
    return r;
  }

  public Map<String, Object> detail(Account a, UUID id) {
    return Map.of("request", mapper.view(participant(a, id)), "decisions", requests.decisions(id));
  }

  public CursorPage<UtilizationView> list(Account a, boolean institution, UUID after) {
    member(a);
    if (institution) organization(a);
    UUID subject = institution ? a.organizationId() : a.id();
    UtilizationRequest cursor =
        after == null ? null : requests.get(after).orElseThrow(UtilizationService::missing);
    if (cursor != null
        && !(institution ? cursor.organizationId() : cursor.ownerId()).equals(subject))
      throw missing();
    var result = requests.list(subject, institution, cursor);
    return new CursorPage<>(
        result.stream().limit(50).map(mapper::view).toList(),
        result.size() > 50 ? result.get(49).id() : null);
  }

  @Transactional
  public UtilizationView create(Account a, CreateUtilizationRequest dto) {
    organization(a);
    var job = jobs.get(dto.jobId()).orElseThrow(UtilizationService::missing);
    research.ownerLock(job.ownerId());
    researchAccess(a, job.id());
    if (job.ownerId().equals(a.id()) || !job.state().equals("SUCCEEDED"))
      throw new DomainException(ErrorCode.CONFLICT);
    String title = dto.title().strip(), purpose = dto.purpose().strip();
    if (title.length() < 2 || purpose.length() < 10)
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    // 배열 순서를 고정해 서버 재시작 후에도 동일한 동의 내용 해시 생성.
    String hash =
        json.hash(
            json.write(
                List.of(
                    POLICY,
                    job.id(),
                    job.versionId(),
                    job.modelHash(),
                    a.organizationId(),
                    title,
                    purpose)));
    var previous = requests.byKey(a.organizationId(), dto.requestKey());
    if (previous.isPresent()) {
      if (!previous.get().termsHash().equals(hash)) throw new UtilizationConflictException();
      return mapper.view(previous.get());
    }
    if (requests.active(job.id(), a.organizationId())) throw new UtilizationConflictException();
    var now = Instant.now();
    var r =
        new UtilizationRequest(
            UUID.randomUUID(),
            job.id(),
            job.versionId(),
            job.modelHash(),
            job.ownerId(),
            a.organizationId(),
            "",
            a.id(),
            dto.requestKey(),
            title,
            purpose,
            POLICY,
            hash,
            "PENDING",
            1,
            now,
            now);
    try {
      requests.add(r);
    } catch (org.springframework.dao.DuplicateKeyException error) {
      throw new UtilizationConflictException();
    }
    research.audit(a.id(), "APPLICATION_REQUESTED", r.id());
    return mapper.view(requests.get(r.id()).orElseThrow());
  }

  @Transactional
  public UtilizationView decide(Account a, UUID id, UtilizationDecisionRequest dto) {
    member(a);
    research.ownerLock(a.id());
    var r = requests.get(id).orElseThrow(UtilizationService::missing);
    if (!r.ownerId().equals(a.id())) throw missing();
    if (r.revision() != dto.expectedRevision() || !r.termsHash().equals(dto.termsHash()))
      throw new UtilizationConflictException();
    String next =
        switch (dto.decision()) {
          case "GRANT" -> r.state().equals("PENDING") ? "GRANTED" : null;
          case "DECLINE" -> r.state().equals("PENDING") ? "DECLINED" : null;
          case "REVOKE" -> r.state().equals("GRANTED") ? "REVOKED" : null;
          default -> null;
        };
    if (next == null) throw new UtilizationConflictException();
    if (next.equals("GRANTED") && !research.approved(r.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    var now = Instant.now();
    if (requests.transition(r, next, now) != 1) throw new UtilizationConflictException();
    requests.decision(r, a.id(), dto.decision(), now);
    research.audit(a.id(), "APPLICATION_" + dto.decision(), id);
    return mapper.view(requests.get(id).orElseThrow());
  }

  public UtilizationRequest grant(Account a, UUID id) {
    organization(a);
    var r = requests.get(id).orElseThrow(UtilizationService::missing);
    if (!r.organizationId().equals(a.organizationId()) || !r.state().equals("GRANTED"))
      throw missing();
    var owner = accounts.byId(r.ownerId()).orElseThrow(UtilizationService::missing);
    var job = jobs.get(r.jobId()).orElseThrow(UtilizationService::missing);
    if (!owner.usable()
        || !owner.role().equals("MEMBER")
        || !job.state().equals("SUCCEEDED")
        || !job.ownerId().equals(r.ownerId())
        || !job.versionId().equals(r.versionId())
        || !job.modelHash().equals(r.modelHash())) throw missing();
    return r;
  }

  public void requireSameGrant(Account a, UtilizationRequest before) {
    var now = grant(a, before.id());
    if (now.revision() != before.revision() || !now.termsHash().equals(before.termsHash()))
      throw new UtilizationConflictException();
  }

  public Map<String, Object> exportScope(UtilizationRequest r) {
    return Map.of(
        "purpose",
        "APPLICATION_REVIEW",
        "requestId",
        r.id(),
        "jobId",
        r.jobId(),
        "versionId",
        r.versionId(),
        "organizationId",
        r.organizationId(),
        "intendedUse",
        r.purpose(),
        "policyVersion",
        r.policyVersion(),
        "termsHash",
        r.termsHash(),
        "consentRevision",
        r.revision(),
        "consentedAt",
        r.updatedAt());
  }

  @Transactional
  public ReviewView addReview(Account a, UUID jobId, CreateStrategyReviewRequest dto) {
    organization(a);
    var job = jobs.get(jobId).orElseThrow(UtilizationService::missing);
    research.ownerLock(job.ownerId());
    researchAccess(a, jobId);
    if (!job.state().equals("SUCCEEDED")) throw new DomainException(ErrorCode.CONFLICT);
    var review =
        new StrategyReview(
            UUID.randomUUID(),
            jobId,
            a.organizationId(),
            "",
            a.id(),
            dto.state(),
            dto.reason().strip(),
            dto.limitations().strip(),
            Instant.now());
    if (review.reason().isEmpty() || review.limitations().isEmpty())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    requests.addReview(review);
    research.audit(a.id(), "STRATEGY_REVIEW_ADDED", review.id());
    return mapper.view(requests.review(review.id()).orElseThrow());
  }

  public CursorPage<ReviewView> reviews(Account a, UUID jobId, UUID after) {
    member(a);
    if (jobId != null) researchAccess(a, jobId);
    StrategyReview cursor =
        after == null ? null : requests.review(after).orElseThrow(UtilizationService::missing);
    if (cursor != null) {
      if (jobId != null) {
        if (!cursor.jobId().equals(jobId) || !cursor.organizationId().equals(a.organizationId()))
          throw missing();
      } else if (jobs.get(cursor.jobId(), a.id()).isEmpty()) throw missing();
    }
    var result = requests.reviews(jobId == null ? a.id() : a.organizationId(), jobId, cursor);
    return new CursorPage<>(
        result.stream().limit(50).map(mapper::view).toList(),
        result.size() > 50 ? result.get(49).id() : null);
  }

  private static DomainException missing() {
    return new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }
}
