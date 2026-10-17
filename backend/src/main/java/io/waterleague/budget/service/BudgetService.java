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
  private final io.waterleague.district.repository.DistrictRepository districts;

  public BudgetService(
      BudgetRepository repository,
      JsonService json,
      io.waterleague.district.repository.DistrictRepository districts)
      throws IOException {
    this.repository = repository;
    this.districts = districts;
    try (var stream = new ClassPathResource("budget/seoul-2026.json").getInputStream()) {
      policy =
          json.read(
              new String(stream.readNBytes(10000), StandardCharsets.UTF_8), BudgetPolicy.class);
    }
    if (policy.districtLimitKrw().signum() <= 0
        || policy.districtCount() != districts.all().size()
        || policy
                .districtLimitKrw()
                .multiply(BigDecimal.valueOf(policy.districtCount()))
                .compareTo(policy.limitKrw())
            != 0
        || !policy.sourceSha256().matches("[a-f0-9]{64}"))
      throw new IllegalStateException("예산 출처 오류");
  }

  public BigDecimal limit() {
    return policy.districtLimitKrw();
  }

  public BudgetPolicy policy() {
    return policy;
  }

  @Transactional(readOnly = true)
  public BudgetView view() {
    var spent = repository.allocatedByDistrict();
    var rows =
        districts.all().stream()
            .map(
                d -> {
                  var allocated = spent.getOrDefault(d.id(), BigDecimal.ZERO);
                  return new BudgetView.DistrictBudget(
                      d.id(),
                      d.name(),
                      allocated,
                      limit().subtract(allocated).max(BigDecimal.ZERO));
                })
            .toList();
    return new BudgetView(
        policy,
        rows.stream()
            .map(BudgetView.DistrictBudget::allocatedKrw)
            .reduce(BigDecimal.ZERO, BigDecimal::add),
        rows.stream()
            .map(BudgetView.DistrictBudget::remainingKrw)
            .reduce(BigDecimal.ZERO, BigDecimal::add),
        rows);
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void lock(String districtId) {
    districts.require(districtId);
    repository.lock(districtId);
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void requireAvailable(String districtId, BigDecimal amount) {
    districts.require(districtId);
    repository.lock(districtId);
    if (amount.signum() < 0 || repository.allocated(districtId).add(amount).compareTo(limit()) > 0)
      throw new DomainException(ErrorCode.BUDGET_EXCEEDED);
  }
}
