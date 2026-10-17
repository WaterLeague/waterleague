package io.waterleague.budget.repository;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BudgetRepository {
  private final JdbcTemplate db;

  public BudgetRepository(JdbcTemplate db) {
    this.db = db;
  }

  public void lock(String districtId) {
    // 같은 구의 설치·철거만 직렬화하여 다른 구의 잔액과 분리.
    db.queryForObject(
        "SELECT pg_advisory_xact_lock(871306,?)", Object.class, Integer.parseInt(districtId));
  }

  public BigDecimal allocated(String districtId) {
    return db.queryForObject(
        "SELECT COALESCE(SUM(cost),0) FROM shared_installations WHERE removed_at IS NULL AND"
            + " district_id=?",
        BigDecimal.class,
        districtId);
  }

  public Map<String, BigDecimal> allocatedByDistrict() {
    var values = new HashMap<String, BigDecimal>();
    db.query(
        "SELECT district_id,SUM(cost) AS allocated FROM shared_installations WHERE removed_at IS"
            + " NULL GROUP BY district_id",
        (org.springframework.jdbc.core.RowCallbackHandler)
            r -> values.put(r.getString("district_id"), r.getBigDecimal("allocated")));
    return values;
  }
}
