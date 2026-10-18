package io.waterleague.installation.repository;

import io.waterleague.installation.entity.SharedInstallation;
import io.waterleague.strategy.entity.FacilityType;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class InstallationRepository {
  private final JdbcTemplate db;
  private final RowMapper<SharedInstallation> mapper =
      (r, n) ->
          new SharedInstallation(
              r.getObject("id", UUID.class),
              r.getString("district_id"),
              r.getString("cell_id"),
              r.getObject("owner_id", UUID.class),
              r.getString("display_name"),
              r.getString("model_hash"),
              FacilityType.valueOf(r.getString("facility_type")),
              r.getBigDecimal("area_m2"),
              r.getBigDecimal("cost"),
              r.getTimestamp("installed_at").toInstant(),
              r.getTimestamp("removed_at") == null
                  ? null
                  : r.getTimestamp("removed_at").toInstant(),
              r.getTimestamp("season_ends_at") == null
                  ? null
                  : r.getTimestamp("season_ends_at").toInstant());

  public InstallationRepository(JdbcTemplate db) {
    this.db = db;
  }

  public List<SharedInstallation> active() {
    return db.query(
        "SELECT i.*,a.display_name FROM shared_installations i JOIN accounts a ON a.id=i.owner_id"
            + " WHERE removed_at IS NULL AND (season_ends_at IS NULL OR"
            + " season_ends_at>CURRENT_TIMESTAMP) ORDER BY district_id,cell_id",
        mapper);
  }

  public List<SharedInstallation> owned(UUID owner) {
    return db.query(
        "SELECT i.*,a.display_name FROM shared_installations i JOIN accounts a ON a.id=i.owner_id"
            + " WHERE removed_at IS NULL AND (season_ends_at IS NULL OR"
            + " season_ends_at>CURRENT_TIMESTAMP) AND owner_id=?",
        mapper,
        owner);
  }

  public Optional<SharedInstallation> find(UUID id) {
    return db
        .query(
            "SELECT i.*,a.display_name FROM shared_installations i JOIN accounts a ON"
                + " a.id=i.owner_id WHERE i.id=?",
            mapper,
            id)
        .stream()
        .findFirst();
  }

  public void add(
      SharedInstallation i,
      String budgetPolicy,
      String admissionSnapshot,
      io.waterleague.cost.entity.CostSnapshot cost) {
    db.update(
        "INSERT INTO"
            + " shared_installations(id,occupied_site,district_id,cell_id,owner_id,model_hash,facility_type,area_m2,cost,installed_at,budget_policy,admission_snapshot,cost_snapshot,cost_snapshot_sha256,season_ends_at)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        i.id(),
        i.ownerId() + ":" + i.districtId() + ":" + i.cellId(),
        i.districtId(),
        i.cellId(),
        i.ownerId(),
        i.modelHash(),
        i.facilityType().name(),
        i.areaM2(),
        i.cost(),
        Timestamp.from(i.installedAt()),
        budgetPolicy,
        admissionSnapshot,
        cost.raw(),
        cost.sha256(),
        i.seasonEndsAt() == null ? null : Timestamp.from(i.seasonEndsAt()));
  }

  public boolean remove(UUID id, UUID owner, Instant at) {
    return db.update(
            "UPDATE shared_installations SET removed_at=?,occupied_site=NULL WHERE id=? AND"
                + " owner_id=? AND removed_at IS NULL",
            Timestamp.from(at),
            id,
            owner)
        == 1;
  }
}
