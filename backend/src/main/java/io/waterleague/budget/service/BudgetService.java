package io.waterleague.budget.service;

import io.waterleague.budget.entity.BudgetAllocationPolicy;
import io.waterleague.budget.entity.BudgetPolicy;
import io.waterleague.budget.exception.BudgetException;
import io.waterleague.budget.mapper.BudgetLedgerMapper;
import io.waterleague.budget.repository.BudgetRepository;
import io.waterleague.budget.view.BudgetAccountingView;
import io.waterleague.budget.view.BudgetLedgerView;
import io.waterleague.budget.view.BudgetView;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.strategy.entity.FacilityType;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class BudgetService {
  private final BudgetRepository repository;
  private final BudgetPolicy policy;
  private final BudgetAllocationPolicy allocationPolicy;
  private final JsonService json;

  public BudgetService(BudgetRepository repository, JsonService json) throws IOException {
    this.repository = repository;
    this.json = json;
    try (var stream = new ClassPathResource("budget/seoul-2026.json").getInputStream()) {
      policy =
          json.read(
              new String(stream.readNBytes(10000), StandardCharsets.UTF_8), BudgetPolicy.class);
    }
    if (policy.personalLimitKrw().compareTo(policy.limitKrw()) != 0
        || policy.limitKrw().compareTo(new BigDecimal("2000000000")) != 0
        || !"MEMBER".equals(policy.allocationScope())
        || !"SEOUL_PERSONAL_FULL_2026_V3".equals(policy.ruleVersion())
        || !policy.sourceSha256().matches("[a-f0-9]{64}"))
      throw new IllegalStateException("예산 출처 오류");
    try (var stream = new ClassPathResource("budget/seoul-accounting-v3.json").getInputStream()) {
      allocationPolicy =
          json.read(
              new String(stream.readNBytes(10000), StandardCharsets.UTF_8),
              BudgetAllocationPolicy.class);
    }
    BudgetAllocationService.validate(allocationPolicy);
    if (!allocationPolicy.budgetRuleVersion().equals(policy.ruleVersion())
        || !allocationPolicy.version().equals("SEOUL_RAINWATER_ACCOUNTING_V3")
        || allocationPolicy.programs().size() != 1
        || !allocationPolicy.programs().getFirst().id().equals("SEOUL_RAINWATER")
        || !allocationPolicy.programs().getFirst().sourceSha256().equals(policy.sourceSha256())
        || allocationPolicy.programs().getFirst().limitKrw().compareTo(limit()) != 0)
      throw new IllegalStateException("예산 사업 연결 오류");
  }

  public BigDecimal limit() {
    return policy.personalLimitKrw();
  }

  public BudgetPolicy policy() {
    return policy;
  }

  @Transactional(readOnly = true)
  public BudgetView view(UUID ownerId) {
    var accounting =
        BudgetAllocationService.calculate(
            allocationPolicy, ownerId == null ? Map.of() : repository.allocatedByFacility(ownerId));
    var allocated =
        accounting.programs().stream()
            .map(BudgetAccountingView.Program::allocatedKrw)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    return new BudgetView(
        policy,
        allocated,
        limit().subtract(allocated).max(BigDecimal.ZERO),
        ownerId != null,
        accounting);
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void lock(UUID ownerId) {
    repository.lock(ownerId);
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void requireAvailable(UUID ownerId, FacilityType type, BigDecimal amount) {
    repository.lock(ownerId);
    var projected = repository.allocatedByFacility(ownerId);
    if (amount == null || amount.signum() <= 0 || amount.scale() > 2)
      throw new BudgetException(ErrorCode.REQUEST_INVALID);
    projected.merge(type, amount, BigDecimal::add);
    validateDesign(projected);
  }

  public BudgetAccountingView validateDesign(Map<FacilityType, BigDecimal> amounts) {
    var accounting = BudgetAllocationService.calculate(allocationPolicy, amounts);
    BudgetAllocationService.requireWithinLimits(accounting);
    return accounting;
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void allocate(UUID ownerId, UUID installationId, FacilityType type) {
    var rule =
        allocationPolicy.facilities().stream()
            .filter(f -> f.facilityType() == type)
            .findFirst()
            .orElseThrow(() -> new BudgetException(ErrorCode.BUDGET_DATA_INVALID));
    repository.allocate(installationId, ownerId, rule.programId(), allocationPolicy.version());
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void release(UUID ownerId, UUID installationId) {
    repository.release(installationId, ownerId);
  }

  @Transactional(readOnly = true)
  public BudgetLedgerView history(UUID ownerId, Long beforeId) {
    if (ownerId == null) throw new BudgetException(ErrorCode.AUTHENTICATION_REQUIRED);
    if (beforeId != null && beforeId <= 0) throw new BudgetException(ErrorCode.REQUEST_INVALID);
    var rows = repository.history(ownerId, beforeId == null ? Long.MAX_VALUE : beforeId);
    var page = rows.stream().limit(50).map(e -> BudgetLedgerMapper.view(e, json)).toList();
    return new BudgetLedgerView(page, rows.size() > 50 ? page.getLast().id() : null);
  }
}
