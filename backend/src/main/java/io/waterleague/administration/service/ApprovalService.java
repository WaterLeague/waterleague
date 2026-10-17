package io.waterleague.administration.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.administration.dto.ReviewRequest;
import io.waterleague.administration.repository.ApprovalRepository;
import io.waterleague.common.exception.*;
import io.waterleague.research.repository.ResearchRepository;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApprovalService {
  private final AccountRepository accounts;
  private final ApprovalRepository approvals;
  private final ResearchRepository research;

  public ApprovalService(AccountRepository a, ApprovalRepository r, ResearchRepository s) {
    accounts = a;
    approvals = r;
    research = s;
  }

  private void admin(Account a) {
    if (!a.role().equals("ADMIN") || !a.usable())
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  public Object list(Account a, String status, String after) {
    admin(a);
    return approvals.list(status, after);
  }

  public Object history(Account a, UUID id) {
    admin(a);
    return approvals.history(id);
  }

  @Transactional
  public Object review(Account a, UUID id, ReviewRequest dto) {
    admin(a);
    if (a.id().equals(id)) throw new DomainException(ErrorCode.ACCESS_DENIED);
    var before =
        accounts.byId(id).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!before.role().equals("MEMBER")) throw new DomainException(ErrorCode.ACCESS_DENIED);
    approvals.lock(id);
    var member = accounts.byId(id).orElseThrow();
    if (!member.enabled() || !member.approvalStatus().equals(dto.expectedStatus()))
      throw new DomainException(ErrorCode.CONFLICT);
    String next =
        switch (dto.decision()) {
          case "APPROVE" -> "APPROVED";
          case "REJECT" -> "REJECTED";
          case "SUSPEND" -> "SUSPENDED";
          default -> throw new DomainException(ErrorCode.REQUEST_INVALID);
        };
    if (next.equals(member.approvalStatus())
        || (next.equals("REJECTED") && !member.approvalStatus().equals("PENDING"))
        || (next.equals("SUSPENDED") && !member.approvalStatus().equals("APPROVED")))
      throw new DomainException(ErrorCode.CONFLICT);
    UUID org = member.organizationId();
    if (next.equals("APPROVED") && member.organizationMember()) {
      if (dto.organizationId() != null) {
        if (!research.approved(dto.organizationId()))
          throw new DomainException(ErrorCode.REQUEST_INVALID);
        org = dto.organizationId();
      } else if (org == null) org = approvals.organization(member.organizationName());
      else if (!research.approved(org)) throw new DomainException(ErrorCode.REQUEST_INVALID);
    } else if (dto.organizationId() != null) throw new DomainException(ErrorCode.REQUEST_INVALID);
    approvals.decide(
        id, a.id(), dto.decision(), next, org, dto.reason().strip(), member.username());
    research.audit(a.id(), "MEMBER_" + dto.decision(), id);
    return Map.of("id", id, "approvalStatus", next);
  }
}
