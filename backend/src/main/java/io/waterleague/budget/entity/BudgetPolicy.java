package io.waterleague.budget.entity;

import java.math.BigDecimal;

public record BudgetPolicy(
    BigDecimal limitKrw,
    int referenceYear,
    String sourceTitle,
    String sourceUrl,
    String sourceSha256,
    String ruleVersion,
    String note) {}
