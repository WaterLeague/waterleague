package io.waterleague.budget.service;

import io.waterleague.budget.entity.BudgetPolicy;
import io.waterleague.budget.repository.BudgetRepository;
import io.waterleague.budget.view.BudgetView;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
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
    if (policy.limitKrw().signum() <= 0 || !policy.sourceSha256().matches("[a-f0-9]{64}"))
      throw new IllegalStateException("예산 출처 오류");
  }

  public BigDecimal limit() {
    return policy.limitKrw();
  }

  @Transactional(readOnly = true)
  public BudgetView view() {
    var allocated = repository.allocated();
    return new BudgetView(policy, allocated, limit().subtract(allocated).max(BigDecimal.ZERO));
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void lock() {
    repository.lock();
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void requireAvailable(BigDecimal amount) {
    repository.lock();
    if (amount.signum() < 0 || repository.allocated().add(amount).compareTo(limit()) > 0)
      throw new DomainException(ErrorCode.BUDGET_EXCEEDED);
  }
}
