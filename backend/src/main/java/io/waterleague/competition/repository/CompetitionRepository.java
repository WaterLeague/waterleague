package io.waterleague.competition.repository;

import io.waterleague.competition.entity.Competition;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class CompetitionRepository {
  private final JdbcTemplate db;
  private static final String SELECT =
      "SELECT c.*,o.name organization_name FROM game_competitions c JOIN organizations o ON"
          + " o.id=c.organization_id";
  private final RowMapper<Competition> mapper =
      (r, n) ->
          new Competition(
              r.getObject("id", UUID.class),
              r.getObject("organization_id", UUID.class),
              r.getObject("created_by", UUID.class),
              r.getString("organization_name"),
              r.getString("title"),
              r.getString("description"),
              r.getString("mode"),
              r.getString("event_id"),
              r.getTimestamp("opens_at").toInstant(),
              r.getTimestamp("closes_at").toInstant(),
              r.getString("rules"),
              r.getString("rules_hash"),
              r.getString("score_policy_sha256"),
              r.getString("state"));

  public CompetitionRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Instant now() {
    return db.queryForObject("SELECT clock_timestamp()", Timestamp.class).toInstant();
  }

  public Optional<Competition> get(UUID id, boolean lock) {
    return db
        .query(SELECT + " WHERE c.id=?" + (lock ? " FOR UPDATE OF c" : ""), mapper, id)
        .stream()
        .findFirst();
  }

  public Optional<Competition> byKey(UUID owner, UUID key) {
    return db
        .query(SELECT + " WHERE c.created_by=? AND c.request_key=?", mapper, owner, key)
        .stream()
        .findFirst();
  }

  public List<Competition> list(int page) {
    return db.query(
        SELECT + " ORDER BY c.created_at DESC,c.id LIMIT 21 OFFSET ?", mapper, page * 20);
  }

  public long active(UUID org) {
    return db.queryForObject(
        "SELECT count(*) FROM game_competitions WHERE organization_id=? AND state='PUBLISHED' AND"
            + " closes_at>clock_timestamp()",
        Long.class,
        org);
  }

  public void lockOrganization(UUID id) {
    db.queryForObject("SELECT id FROM organizations WHERE id=? FOR UPDATE", UUID.class, id);
  }

  public void add(Competition c, UUID key) {
    db.update(
        "INSERT INTO"
            + " game_competitions(id,organization_id,created_by,request_key,title,description,mode,event_id,opens_at,closes_at,rules,rules_hash,score_policy_sha256,state)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        c.id(),
        c.organizationId(),
        c.createdBy(),
        key,
        c.title(),
        c.description(),
        c.mode(),
        c.eventId(),
        Timestamp.from(c.opensAt()),
        Timestamp.from(c.closesAt()),
        c.rules(),
        c.rulesHash(),
        c.scorePolicySha256(),
        c.state());
  }

  public void cancel(UUID id) {
    db.update("UPDATE game_competitions SET state='CANCELLED' WHERE id=?", id);
  }

  public Instant joined(UUID id, UUID owner) {
    return db
        .query(
            "SELECT joined_at FROM game_competition_participants WHERE competition_id=? AND"
                + " owner_id=?",
            (r, n) -> r.getTimestamp(1).toInstant(),
            id,
            owner)
        .stream()
        .findFirst()
        .orElse(null);
  }

  public long participants(UUID id) {
    return db.queryForObject(
        "SELECT count(*) FROM game_competition_participants WHERE competition_id=?",
        Long.class,
        id);
  }

  public void join(UUID id, UUID owner, String hash) {
    db.update(
        "INSERT INTO game_competition_participants(competition_id,owner_id,rules_hash)"
            + " VALUES(?,?,?)",
        id,
        owner,
        hash);
  }

  public boolean entered(UUID id, UUID job, UUID owner) {
    return db.queryForObject(
            "SELECT count(*) FROM game_competition_submissions WHERE competition_id=? AND job_id=?"
                + " AND owner_id=?",
            Integer.class,
            id,
            job,
            owner)
        > 0;
  }

  public void submit(UUID id, UUID owner, UUID job) {
    db.update(
        "INSERT INTO game_competition_submissions(competition_id,owner_id,job_id) VALUES(?,?,?)",
        id,
        owner,
        job);
  }

  public List<Map<String, Object>> historicalJobs(UUID owner, String event) {
    return db.query(
        "SELECT"
            + " j.id,j.state,j.placements,j.created_at,s.score_policy_sha256,s.difference_m3,s.rules_hash,s.comparison_group_hash"
            + " FROM historical_experiments j JOIN historical_submissions s ON s.job_id=j.id WHERE"
            + " j.owner_id=? AND s.event_id=? AND j.source_dataset='SEOUL_NGII_GAME_V2' ORDER BY"
            + " j.created_at DESC,j.id LIMIT 100",
        (r, n) -> {
          var v = new LinkedHashMap<String, Object>();
          v.put("id", r.getObject("id", UUID.class));
          v.put("state", r.getString("state"));
          v.put("placements", r.getString("placements"));
          v.put("createdAt", r.getTimestamp("created_at").toInstant());
          v.put("policy", r.getString("score_policy_sha256"));
          return v;
        },
        owner,
        event);
  }

  public List<Map<String, Object>> disasterRows(UUID id) {
    return db.query(
        """
        SELECT * FROM (SELECT p.owner_id,a.display_name,j.id job_id,j.state,s.difference_m3 score,
          s.comparison_group_hash,s.score_policy_sha256,s.rules_hash,j.created_at,
          ROW_NUMBER() OVER(PARTITION BY p.owner_id,s.rules_hash,s.comparison_group_hash ORDER BY s.difference_m3 DESC NULLS LAST,j.created_at,j.id) choice
        FROM game_competition_participants p JOIN accounts a ON a.id=p.owner_id
        JOIN game_competition_submissions e ON e.competition_id=p.competition_id AND e.owner_id=p.owner_id
        JOIN historical_experiments j ON j.id=e.job_id JOIN historical_submissions s ON s.job_id=j.id
        WHERE p.competition_id=? AND a.enabled=true AND a.approval_status='APPROVED') ranked WHERE choice=1
        """,
        (r, n) -> {
          var v = new LinkedHashMap<String, Object>();
          v.put("playerId", r.getObject("owner_id", UUID.class));
          v.put("nickname", r.getString("display_name"));
          v.put("scoreM3", r.getBigDecimal("score"));
          v.put("group", r.getString("rules_hash") + ":" + r.getString("comparison_group_hash"));
          v.put("policy", r.getString("score_policy_sha256"));
          v.put(
              "comparable",
              r.getString("state").equals("SUCCEEDED")
                  && r.getString("comparison_group_hash") != null
                  && r.getBigDecimal("score") != null);
          v.put("submittedAt", r.getTimestamp("created_at").toInstant());
          return v;
        },
        id);
  }

  public long pendingDisaster(UUID id) {
    return db.queryForObject(
        "SELECT count(*) FROM game_competition_submissions e JOIN historical_experiments j ON"
            + " j.id=e.job_id WHERE e.competition_id=? AND j.state IN ('QUEUED','RUNNING')",
        Long.class,
        id);
  }

  public List<Map<String, Object>> liveInstallations(UUID id, Instant target) {
    return db.query(
        """
        SELECT i.id,i.owner_id,a.display_name,i.district_id,i.facility_type,i.installed_at,i.area_m2,
          s.score_m3,s.evaluated_seconds,s.comparison_group_hash,s.score_policy_sha256,
          GREATEST(0,EXTRACT(EPOCH FROM (LEAST(c.closes_at,COALESCE(i.removed_at,i.season_ends_at,c.closes_at),?::timestamptz)-i.installed_at)))::bigint expected_seconds
        FROM game_competitions c JOIN game_competition_participants p ON p.competition_id=c.id
        JOIN accounts a ON a.id=p.owner_id JOIN shared_installations i ON i.owner_id=p.owner_id
        LEFT JOIN game_competition_live_scores s ON s.competition_id=c.id AND s.installation_id=i.id
        WHERE c.id=? AND i.installed_at>=c.opens_at AND i.installed_at>=p.joined_at AND i.installed_at<c.closes_at
          AND i.physics_policy='INSTALLATION_SECOND_V2' AND a.enabled=true AND a.approval_status='APPROVED'
          AND jsonb_exists(c.rules::jsonb->'districtIds',i.district_id) AND jsonb_exists(c.rules::jsonb->'allowedTypes',i.facility_type)
        ORDER BY i.owner_id,i.installed_at,i.id
        """,
        (r, n) -> {
          var v = new LinkedHashMap<String, Object>();
          v.put("id", r.getObject("id", UUID.class));
          v.put("playerId", r.getObject("owner_id", UUID.class));
          v.put("nickname", r.getString("display_name"));
          v.put("districtId", r.getString("district_id"));
          v.put("facilityType", r.getString("facility_type"));
          v.put("areaM2", r.getBigDecimal("area_m2"));
          v.put("installedAt", r.getTimestamp("installed_at").toInstant());
          v.put("scoreM3", r.getBigDecimal("score_m3"));
          v.put("evaluatedSeconds", r.getLong("evaluated_seconds"));
          v.put("expectedSeconds", r.getLong("expected_seconds"));
          v.put("group", r.getString("comparison_group_hash"));
          v.put("policy", r.getString("score_policy_sha256"));
          return v;
        },
        Timestamp.from(target),
        id);
  }
}
