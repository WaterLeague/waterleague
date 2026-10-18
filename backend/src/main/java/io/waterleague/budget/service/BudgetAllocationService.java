package io.waterleague.budget.service;

import io.waterleague.budget.entity.BudgetAllocationPolicy;
import io.waterleague.budget.exception.BudgetException;
import io.waterleague.budget.view.BudgetAccountingView;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;

public final class BudgetAllocationService {
  private BudgetAllocationService() {}

  public static void validate(BudgetAllocationPolicy policy) {
    var ids = new HashSet<String>();
    var types = EnumSet.noneOf(FacilityType.class);
    if (policy.programs().isEmpty() || policy.facilities().isEmpty()) invalid();
    for (var p : policy.programs()) {
      if (p.id() == null
          || !p.id().matches("[A-Z][A-Z0-9_]{0,63}")
          || !ids.add(p.id())
          || p.name() == null
          || p.name().isBlank()
          || !amount(p.limitKrw())
          || p.limitKrw().signum() == 0
          || p.sourceSha256() == null
          || !p.sourceSha256().matches("[a-f0-9]{64}")) invalid();
    }
    for (var f : policy.facilities()) {
      if (f.facilityType() == null
          || !types.add(f.facilityType())
          || !ids.contains(f.programId())
          || (f.limitKrw() != null && !amount(f.limitKrw()))) invalid();
    }
    if (policy.programs().stream()
        .anyMatch(p -> policy.facilities().stream().noneMatch(f -> f.programId().equals(p.id()))))
      invalid();
  }

  private static boolean amount(BigDecimal n) {
    return n != null && n.signum() >= 0 && n.scale() <= 2;
  }

  private static void invalid() {
    throw new BudgetException(ErrorCode.BUDGET_DATA_INVALID);
  }

  public static BudgetAccountingView calculate(
      BudgetAllocationPolicy policy, Map<FacilityType, BigDecimal> spent) {
    var configured = EnumSet.noneOf(FacilityType.class);
    policy.facilities().forEach(f -> configured.add(f.facilityType()));
    if (!configured.containsAll(spent.keySet())
        || spent.values().stream().anyMatch(n -> !amount(n))) invalid();
    var programs = new ArrayList<BudgetAccountingView.Program>();
    var remaining = new HashMap<String, BigDecimal>();
    for (var p : policy.programs()) {
      var used =
          policy.facilities().stream()
              .filter(f -> f.programId().equals(p.id()))
              .map(f -> spent.getOrDefault(f.facilityType(), BigDecimal.ZERO))
              .reduce(BigDecimal.ZERO, BigDecimal::add);
      var available = p.limitKrw().subtract(used).max(BigDecimal.ZERO);
      programs.add(
          new BudgetAccountingView.Program(
              p.id(), p.name(), p.limitKrw(), used, available, p.sourceSha256()));
      remaining.put(p.id(), available);
    }
    var facilities =
        policy.facilities().stream()
            .map(
                f -> {
                  var used = spent.getOrDefault(f.facilityType(), BigDecimal.ZERO);
                  var available = remaining.get(f.programId());
                  if (f.limitKrw() != null)
                    available = available.min(f.limitKrw().subtract(used).max(BigDecimal.ZERO));
                  return new BudgetAccountingView.Facility(
                      f.facilityType(), f.programId(), f.limitKrw(), used, available);
                })
            .toList();
    return new BudgetAccountingView(policy.version(), List.copyOf(programs), facilities);
  }

  public static void requireWithinLimits(BudgetAccountingView accounting) {
    if (accounting.programs().stream().anyMatch(p -> p.allocatedKrw().compareTo(p.limitKrw()) > 0)
        || accounting.facilities().stream()
            .anyMatch(f -> f.limitKrw() != null && f.allocatedKrw().compareTo(f.limitKrw()) > 0))
      throw new BudgetException(ErrorCode.BUDGET_EXCEEDED);
  }
}
