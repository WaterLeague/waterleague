package io.waterleague.budget.entity;

import java.time.Instant;
import java.util.List;

public record InstallationLedger(Instant removedAt, List<BudgetLedgerEntry> entries) {}
