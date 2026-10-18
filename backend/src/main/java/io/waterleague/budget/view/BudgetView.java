package io.waterleague.budget.view;

import io.waterleague.budget.entity.BudgetPolicy;
import java.math.BigDecimal;

public record BudgetView(
    BudgetPolicy policy,
    BigDecimal allocatedKrw,
    BigDecimal remainingKrw,
    boolean personal,
    BudgetAccountingView accounting) {}
