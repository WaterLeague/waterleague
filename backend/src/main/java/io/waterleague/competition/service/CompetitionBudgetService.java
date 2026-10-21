package io.waterleague.competition.service;

import io.waterleague.account.repository.AccountRepository;
import io.waterleague.budget.entity.BudgetPolicy;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.competition.entity.Competition;
import io.waterleague.competition.repository.CompetitionRepository;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.strategy.entity.FacilityType;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class CompetitionBudgetService {
  private final CompetitionRepository competitions;
  private final AccountRepository accounts;
  private final ResearchRepository organizations;
  private final BudgetService budget;
  private final JsonService json;

  public CompetitionBudgetService(
      CompetitionRepository competitions,
      AccountRepository accounts,
      ResearchRepository organizations,
      BudgetService budget,
      JsonService json) {
    this.competitions = competitions;
    this.accounts = accounts;
    this.organizations = organizations;
    this.budget = budget;
    this.json = json;
  }

  public Competition require(UUID owner, UUID id, String mode, String event, boolean write) {
    if (id == null) return null;
    var account =
        accounts.byId(owner).orElseThrow(() -> new DomainException(ErrorCode.ACCESS_DENIED));
    var c =
        competitions
            .get(id, write)
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!account.usable()
        || !"PLAYER".equals(account.memberType())
        || !"MEMBER".equals(account.role())
        || competitions.joined(id, owner) == null)
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    if (!json.hash(c.rules()).equals(c.rulesHash()))
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    if (mode != null && (!mode.equals(c.mode()) || !Objects.equals(event, c.eventId())))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var now = competitions.now();
    if (write
        && (!"PUBLISHED".equals(c.state())
            || now.isBefore(c.opensAt())
            || !now.isBefore(c.closesAt())
            || !organizations.approved(c.organizationId())))
      throw new DomainException(ErrorCode.CONFLICT);
    return c;
  }

  public void requireViewer(UUID owner, UUID id) {
    var account =
        accounts.byId(owner).orElseThrow(() -> new DomainException(ErrorCode.ACCESS_DENIED));
    var c =
        competitions
            .get(id, false)
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!account.usable()
        || !("ADMIN".equals(account.role())
            || account.organizationMember()
                && Objects.equals(account.organizationId(), c.organizationId())
                && organizations.approved(c.organizationId())
            || competitions.joined(id, owner) != null))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  public void permits(Competition c, String district, FacilityType type) {
    if (c == null) return;
    var rules = json.tree(c.rules());
    boolean region = false, facility = false;
    for (var v : rules.path("districtIds")) region |= v.asString().equals(district);
    for (var v : rules.path("allowedTypes")) facility |= v.asString().equals(type.name());
    if (!region || !facility) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
  }

  public BudgetPolicy policy(Competition c) {
    if (c == null) return budget.policy();
    var amount = json.tree(c.rules()).path("personalBudgetKrw");
    var limit = amount.isNumber() ? amount.decimalValue() : budget.limit();
    if (limit.signum() <= 0 || limit.compareTo(new java.math.BigDecimal("1000000000000")) > 0)
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    return new BudgetPolicy(
        limit,
        limit,
        "MEMBER",
        c.opensAt().atZone(java.time.ZoneId.of("Asia/Seoul")).getYear(),
        c.title() + " · 1인당 예산",
        "https://waterleague.cloud/competitions/" + c.id(),
        c.rulesHash(),
        "COMPETITION_PERSONAL_V1",
        "주최자가 확정한 대회별 개인 게임 예산. 일반 게임 및 다른 대회와 별도 사용.");
  }
}
