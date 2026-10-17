package io.waterleague.budget.repository;

import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BudgetRepository {
  private final JdbcTemplate db;

  public BudgetRepository(JdbcTemplate db) {
    this.db = db;
  }

  public void lock() {
    // 서로 다른 계정의 배치도 같은 예산 한도를 사용하므로 공통 트랜잭션 잠금 적용.
    db.execute("SELECT pg_advisory_xact_lock(871306,1)");
  }

  public BigDecimal allocated() {
    return db.queryForObject(
        "SELECT COALESCE(SUM(cost),0) FROM shared_installations WHERE removed_at IS NULL",
        BigDecimal.class);
  }
}
