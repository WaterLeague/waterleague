package io.waterleague.budget.repository;

import java.math.BigDecimal;
import java.util.UUID;
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

  public BigDecimal allocated(UUID ownerId) {
    return db.queryForObject(
        "SELECT COALESCE(SUM(cost),0) FROM shared_installations WHERE removed_at IS NULL AND"
            + " owner_id=?",
        BigDecimal.class,
        ownerId);
  }
}
