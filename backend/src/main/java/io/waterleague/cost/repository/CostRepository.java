package io.waterleague.cost.repository;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CostRepository {
  public record Record(
      String raw,
      String sha256,
      String districtId,
      String cellId,
      String modelHash,
      String facilityType,
      BigDecimal areaM2,
      BigDecimal cost) {}

  private final JdbcTemplate db;

  public CostRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<Record> active(UUID id) {
    return db
        .query(
            "SELECT"
                + " cost_snapshot,cost_snapshot_sha256,district_id,cell_id,model_hash,facility_type,area_m2,cost"
                + " FROM shared_installations WHERE id=? AND removed_at IS NULL",
            (r, n) ->
                new Record(
                    r.getString("cost_snapshot"),
                    r.getString("cost_snapshot_sha256"),
                    r.getString("district_id"),
                    r.getString("cell_id"),
                    r.getString("model_hash"),
                    r.getString("facility_type"),
                    r.getBigDecimal("area_m2"),
                    r.getBigDecimal("cost")),
            id)
        .stream()
        .findFirst();
  }
}
