package io.waterleague.budget.mapper;

import io.waterleague.budget.entity.BudgetLedgerEntry;
import io.waterleague.budget.view.BudgetLedgerView;
import io.waterleague.common.service.JsonService;

public final class BudgetLedgerMapper {
  private BudgetLedgerMapper() {}

  public static BudgetLedgerView.Entry view(BudgetLedgerEntry e, JsonService json) {
    return new BudgetLedgerView.Entry(
        Long.toString(e.id()),
        e.installationId(),
        e.programId(),
        e.facilityType(),
        e.eventType(),
        e.amountKrw(),
        e.effectiveAt(),
        e.recordedAt(),
        e.provenance(),
        e.accountingVersion(),
        e.sourceBudgetPolicy() == null ? null : json.tree(e.sourceBudgetPolicy()));
  }
}
