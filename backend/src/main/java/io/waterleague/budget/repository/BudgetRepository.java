package io.waterleague.budget.repository;

import io.waterleague.budget.entity.BudgetLedgerEntry;
import io.waterleague.budget.exception.BudgetException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BudgetRepository {
  private final JdbcTemplate db;

  public BudgetRepository(JdbcTemplate db) {
    this.db = db;
  }

  public void lock(UUID ownerId) {
    // 같은 회원의 설치·철거를 직렬화하고 다른 회원의 예산은 독립 처리.
    db.queryForObject("SELECT id FROM accounts WHERE id=? FOR UPDATE", UUID.class, ownerId);
  }

  public Map<FacilityType, BigDecimal> allocatedByFacility(UUID ownerId) {
    var amounts = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    db.query(
        "SELECT facility_type,SUM(CASE WHEN event_type='ALLOCATE' THEN amount_krw ELSE -amount_krw"
            + " END) AS allocated FROM budget_ledger_entries WHERE owner_id=? GROUP BY"
            + " facility_type",
        (org.springframework.jdbc.core.RowCallbackHandler)
            r ->
                amounts.put(
                    FacilityType.valueOf(r.getString("facility_type")),
                    r.getBigDecimal("allocated")),
        ownerId);
    return amounts;
  }

  public void allocate(UUID installationId, UUID ownerId, String programId, String version) {
    int inserted =
        db.update(
            """
            INSERT INTO budget_ledger_entries(installation_id,owner_id,program_id,facility_type,event_type,amount_krw,effective_at,provenance,accounting_version,source_budget_policy)
            SELECT id,owner_id,?,facility_type,'ALLOCATE',cost,installed_at,'LIVE_TRANSACTION',?,budget_policy
            FROM shared_installations WHERE id=? AND owner_id=? AND removed_at IS NULL
            """,
            programId,
            version,
            installationId,
            ownerId);
    if (inserted != 1) throw new BudgetException(ErrorCode.BUDGET_DATA_INVALID);
  }

  public void release(UUID installationId, UUID ownerId) {
    // 취소액은 현재 단가가 아니라 최초 배정 원장에서 복사한다.
    int inserted =
        db.update(
            """
            INSERT INTO budget_ledger_entries(installation_id,owner_id,program_id,facility_type,event_type,amount_krw,effective_at,provenance,accounting_version,source_budget_policy)
            SELECT e.installation_id,e.owner_id,e.program_id,e.facility_type,'RELEASE',e.amount_krw,i.removed_at,'LIVE_TRANSACTION',e.accounting_version,e.source_budget_policy
            FROM budget_ledger_entries e JOIN shared_installations i ON i.id=e.installation_id
            WHERE e.installation_id=? AND e.owner_id=? AND e.event_type='ALLOCATE' AND i.removed_at IS NOT NULL
            """,
            installationId,
            ownerId);
    if (inserted != 1) throw new BudgetException(ErrorCode.BUDGET_DATA_INVALID);
  }

  public List<BudgetLedgerEntry> history(UUID ownerId, long beforeId) {
    return db.query(
        "SELECT * FROM budget_ledger_entries WHERE owner_id=? AND id<? ORDER BY id DESC LIMIT 51",
        (r, n) ->
            new BudgetLedgerEntry(
                r.getLong("id"),
                r.getObject("installation_id", UUID.class),
                r.getString("program_id"),
                FacilityType.valueOf(r.getString("facility_type")),
                r.getString("event_type"),
                r.getBigDecimal("amount_krw"),
                r.getTimestamp("effective_at").toInstant(),
                r.getTimestamp("recorded_at").toInstant(),
                r.getString("provenance"),
                r.getString("accounting_version"),
                r.getString("source_budget_policy")),
        ownerId,
        beforeId);
  }
}
