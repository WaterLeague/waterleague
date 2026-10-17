package io.waterleague.budget.service;

import io.waterleague.budget.entity.BudgetPolicy;
import io.waterleague.budget.repository.BudgetRepository;
import io.waterleague.budget.view.BudgetView;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class BudgetService {
  private final BudgetRepository repository;
  private final BudgetPolicy policy;

  public BudgetService(BudgetRepository repository, JsonService json) throws IOException {
    this.repository = repository;
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
  }

  public BigDecimal limit() {
    return policy.personalLimitKrw();
  }

  public BudgetPolicy policy() {
    return policy;
  }

  @Transactional(readOnly = true)
  public BudgetView view(UUID ownerId) {
    var allocated = ownerId == null ? BigDecimal.ZERO : repository.allocated(ownerId);
    return new BudgetView(
        policy, allocated, limit().subtract(allocated).max(BigDecimal.ZERO), ownerId != null);
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void lock(UUID ownerId) {
    repository.lock(ownerId);
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void requireAvailable(UUID ownerId, BigDecimal amount) {
    repository.lock(ownerId);
    if (amount.signum() < 0 || repository.allocated(ownerId).add(amount).compareTo(limit()) > 0)
      throw new DomainException(ErrorCode.BUDGET_EXCEEDED);
  }
}
