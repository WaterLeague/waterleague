package io.waterleague.gameanalysis.repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class GameAnalysisRepository {
  private final JdbcTemplate db;

  public GameAnalysisRepository(JdbcTemplate db) {
    this.db = db;
  }

  public List<Map<String, Object>> weekly(
      Instant start, Instant through, java.time.LocalDate week) {
    return db.queryForList(
        """
        SELECT i.id,i.owner_id,i.district_id,i.facility_type,i.area_m2,i.installed_at created_at,s.score_m3
        FROM shared_installations i LEFT JOIN shared_weekly_scores s ON s.installation_id=i.id AND s.week_start=?
        WHERE i.competition_id IS NULL AND i.installed_at<?
          AND COALESCE(i.removed_at,i.season_ends_at,'infinity'::timestamptz)>?
        ORDER BY i.id
        """,
        java.sql.Date.valueOf(week),
        Timestamp.from(through),
        Timestamp.from(start));
  }

  public List<Map<String, Object>> historical(String event, UUID competition) {
    return db.queryForList(
        """
        SELECT j.id,j.owner_id,j.state,j.created_at,j.placements,s.difference_m3,s.comparison_group_hash,s.score_policy_sha256
        FROM historical_experiments j JOIN historical_submissions s ON s.job_id=j.id
        JOIN accounts a ON a.id=j.owner_id
        WHERE j.source_dataset='SEOUL_NGII_GAME_V2' AND a.enabled=true AND a.approval_status='APPROVED'
          AND s.event_id=? AND ((?::uuid IS NULL AND j.competition_id IS NULL) OR EXISTS(
            SELECT 1 FROM game_competition_submissions e WHERE e.competition_id=?::uuid AND e.job_id=j.id AND e.owner_id=j.owner_id))
        ORDER BY j.id
        """,
        event,
        competition,
        competition);
  }
}
