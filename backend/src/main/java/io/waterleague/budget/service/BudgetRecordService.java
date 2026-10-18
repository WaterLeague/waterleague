package io.waterleague.budget.service;

import io.waterleague.budget.dto.BudgetRecordRequest;
import io.waterleague.budget.entity.BudgetLedgerEntry;
import io.waterleague.budget.exception.BudgetException;
import io.waterleague.budget.mapper.BudgetLedgerMapper;
import io.waterleague.budget.repository.BudgetRepository;
import io.waterleague.budget.view.BudgetRecordEvidence;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class BudgetRecordService {
  private final BudgetRepository repository;
  private final JsonService json;

  public BudgetRecordService(BudgetRepository repository, JsonService json) {
    this.repository = repository;
    this.json = json;
  }

  public BudgetRecordEvidence snapshot(BudgetRecordRequest request) {
    try {
      var history = repository.installationHistory(request.ownerId(), request.installationId());
      var captured = Instant.now();
      var entries = history.entries();
      if (entries.isEmpty())
        return new BudgetRecordEvidence(
            1,
            request.calculationId(),
            request.installationId(),
            captured,
            request.evaluatedThrough(),
            "NOT_RECORDED",
            "EFFECTIVE_EVENT_TIME",
            request.costKrw(),
            null,
            null,
            history.removedAt(),
            List.of());
      var allocate = entries.getFirst();
      check(
          allocate.eventType().equals("ALLOCATE")
              && allocate.effectiveAt().equals(request.installedAt())
              && !request.evaluatedThrough().isBefore(request.installedAt())
              && (history.removedAt() == null ? entries.size() == 1 : entries.size() == 2));
      for (var entry : entries) {
        check(
            entry.installationId().equals(request.installationId())
                && entry.facilityType() == request.facilityType()
                && entry.amountKrw().compareTo(request.costKrw()) == 0
                && entry.amountKrw().signum() > 0
                && !entry.effectiveAt().isAfter(captured)
                && (entry.sourceBudgetPolicy() == null
                    || entry.sourceBudgetPolicy().length() <= 65536));
      }
      if (entries.size() == 2) {
        var release = entries.getLast();
        check(
            release.eventType().equals("RELEASE")
                && release.effectiveAt().equals(history.removedAt())
                && !release.effectiveAt().isBefore(allocate.effectiveAt())
                && release.programId().equals(allocate.programId())
                && release.accountingVersion().equals(allocate.accountingVersion())
                && Objects.equals(release.sourceBudgetPolicy(), allocate.sourceBudgetPolicy()));
      }
      BigDecimal atEvaluation = BigDecimal.ZERO, atCapture = BigDecimal.ZERO;
      for (BudgetLedgerEntry entry : entries) {
        var signed =
            entry.eventType().equals("ALLOCATE") ? entry.amountKrw() : entry.amountKrw().negate();
        atCapture = atCapture.add(signed);
        if (!entry.effectiveAt().isAfter(request.evaluatedThrough()))
          atEvaluation = atEvaluation.add(signed);
      }
      return new BudgetRecordEvidence(
          1,
          request.calculationId(),
          request.installationId(),
          captured,
          request.evaluatedThrough(),
          "AVAILABLE",
          "EFFECTIVE_EVENT_TIME",
          request.costKrw(),
          atEvaluation,
          atCapture,
          history.removedAt(),
          entries.stream().map(e -> BudgetLedgerMapper.view(e, json)).toList());
    } catch (RuntimeException e) {
      throw new BudgetException(ErrorCode.BUDGET_DATA_INVALID);
    }
  }

  private void check(boolean valid) {
    if (!valid) throw new BudgetException(ErrorCode.BUDGET_DATA_INVALID);
  }
}
