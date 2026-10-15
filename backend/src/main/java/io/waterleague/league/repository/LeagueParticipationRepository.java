package io.waterleague.league.repository;

import io.waterleague.league.entity.*;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class LeagueParticipationRepository {
  private final JdbcTemplate db;
  private final RowMapper<LeagueParticipant> participant =
      (rs, n) ->
          new LeagueParticipant(
              rs.getObject("league_id", UUID.class),
              rs.getObject("owner_id", UUID.class),
              rs.getString("display_name"),
              rs.getString("state"),
              rs.getInt("revision"),
              rs.getBoolean("review_required"),
              rs.getString("rules_hash"),
              rs.getTimestamp("created_at").toInstant(),
              rs.getTimestamp("updated_at").toInstant());
  private final RowMapper<LeagueTeam> team =
      (rs, n) ->
          new LeagueTeam(
              rs.getObject("id", UUID.class),
              rs.getObject("league_id", UUID.class),
              rs.getObject("captain_id", UUID.class),
              rs.getString("name"),
              rs.getTimestamp("frozen_at") == null
                  ? null
                  : rs.getTimestamp("frozen_at").toInstant());
  private static final String PEOPLE =
      "SELECT p.*,a.display_name FROM league_participants p JOIN accounts a ON a.id=p.owner_id ";

  public LeagueParticipationRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<LeagueParticipant> get(UUID league, UUID owner) {
    return db
        .query(PEOPLE + "WHERE p.league_id=? AND p.owner_id=?", participant, league, owner)
        .stream()
        .findFirst();
  }

  public List<LeagueParticipant> page(UUID league, UUID after) {
    return after == null
        ? db.query(
            PEOPLE + "WHERE p.league_id=? ORDER BY p.owner_id LIMIT 101", participant, league)
        : db.query(
            PEOPLE + "WHERE p.league_id=? AND p.owner_id>? ORDER BY p.owner_id LIMIT 101",
            participant,
            league,
            after);
  }

  public List<UUID> joined(UUID owner) {
    return db.query(
        "SELECT p.league_id FROM league_participants p JOIN leagues l ON l.id=p.league_id JOIN"
            + " organizations o ON o.id=l.organization_id WHERE p.owner_id=? AND p.state IN"
            + " ('PENDING','APPROVED') AND o.approved=true AND l.state<>'DRAFT' ORDER BY"
            + " p.updated_at DESC,p.league_id LIMIT 100",
        (rs, n) -> rs.getObject(1, UUID.class),
        owner);
  }

  public int size(UUID league) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM league_participants WHERE league_id=?", Integer.class, league);
  }

  public void change(
      UUID league, UUID owner, UUID actor, String state, String hash, String reason) {
    Instant now = Instant.now();
    int updated =
        db.update(
            "UPDATE league_participants SET state=?,rules_hash=?,revision=revision+1,updated_at=?"
                + " WHERE league_id=? AND owner_id=?",
            state,
            hash,
            Timestamp.from(now),
            league,
            owner);
    if (updated == 0)
      db.update(
          "INSERT INTO"
              + " league_participants(league_id,owner_id,state,revision,rules_hash,created_at,updated_at)"
              + " VALUES(?,?,?,1,?,?,?)",
          league,
          owner,
          state,
          hash,
          Timestamp.from(now),
          Timestamp.from(now));
    var p = get(league, owner).orElseThrow();
    db.update(
        "INSERT INTO"
            + " league_participant_events(id,league_id,owner_id,actor_id,revision,state,reason,created_at)"
            + " VALUES(?,?,?,?,?,?,?,?)",
        UUID.randomUUID(),
        league,
        owner,
        actor,
        p.revision(),
        state,
        reason,
        Timestamp.from(now));
  }

  public void reviewRequired(UUID league, UUID owner, boolean required) {
    db.update(
        "UPDATE league_participants SET review_required=? WHERE league_id=? AND owner_id=?",
        required,
        league,
        owner);
  }

  public List<Map<String, Object>> events(UUID league, UUID owner) {
    return db.query(
        "SELECT revision,state,reason,created_at FROM league_participant_events WHERE league_id=?"
            + " AND owner_id=? ORDER BY revision DESC LIMIT 100",
        (rs, n) ->
            Map.of(
                "revision",
                rs.getInt("revision"),
                "state",
                rs.getString("state"),
                "reason",
                rs.getString("reason"),
                "createdAt",
                rs.getTimestamp("created_at").toInstant()),
        league,
        owner);
  }

  public void invite(UUID league, String hash, Instant expires) {
    db.update("DELETE FROM league_invitations WHERE league_id=?", league);
    if (hash != null)
      db.update(
          "INSERT INTO league_invitations(league_id,token_hash,expires_at) VALUES(?,?,?)",
          league,
          hash,
          Timestamp.from(expires));
  }

  public Optional<UUID> invited(String hash, Instant now) {
    return db
        .query(
            "SELECT league_id FROM league_invitations WHERE token_hash=? AND expires_at>?",
            (rs, n) -> rs.getObject(1, UUID.class),
            hash,
            Timestamp.from(now))
        .stream()
        .findFirst();
  }

  public boolean hasInvite(UUID league) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM league_invitations WHERE league_id=? AND expires_at>?",
            Integer.class,
            league,
            Timestamp.from(Instant.now()))
        > 0;
  }

  public Optional<LeagueTeam> ownTeam(UUID league, UUID owner) {
    return db
        .query(
            "SELECT t.* FROM league_teams t JOIN league_team_members m ON m.team_id=t.id AND"
                + " m.league_id=t.league_id WHERE m.league_id=? AND m.owner_id=?",
            team,
            league,
            owner)
        .stream()
        .findFirst();
  }

  public Optional<LeagueTeam> invitedTeam(UUID league, String hash) {
    return db
        .query("SELECT * FROM league_teams WHERE league_id=? AND token_hash=?", team, league, hash)
        .stream()
        .findFirst();
  }

  public boolean nameExists(UUID league, String name) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM league_teams WHERE league_id=? AND name=?",
            Integer.class,
            league,
            name)
        > 0;
  }

  public LeagueTeam createTeam(UUID league, UUID owner, String name, String hash) {
    UUID id = UUID.randomUUID();
    db.update(
        "INSERT INTO league_teams(id,league_id,captain_id,name,token_hash,created_at)"
            + " VALUES(?,?,?,?,?,?)",
        id,
        league,
        owner,
        name,
        hash,
        Timestamp.from(Instant.now()));
    joinTeam(league, id, owner);
    return ownTeam(league, owner).orElseThrow();
  }

  public void joinTeam(UUID league, UUID team, UUID owner) {
    db.update(
        "INSERT INTO league_team_members(league_id,team_id,owner_id,joined_at) VALUES(?,?,?,?)",
        league,
        team,
        owner,
        Timestamp.from(Instant.now()));
  }

  public int teamSize(UUID team) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM league_team_members WHERE team_id=?", Integer.class, team);
  }

  public List<Map<String, Object>> roster(LeagueTeam team, UUID viewer) {
    return db.query(
        "SELECT a.id,a.display_name,a.enabled,a.approval_status,p.state FROM league_team_members m"
            + " JOIN accounts a ON a.id=m.owner_id JOIN league_participants p ON"
            + " p.league_id=m.league_id AND p.owner_id=m.owner_id WHERE m.team_id=? ORDER BY"
            + " m.joined_at,m.owner_id",
        (rs, n) ->
            Map.of(
                "displayName",
                rs.getString("display_name"),
                "captain",
                team.captainId().equals(rs.getObject("id", UUID.class)),
                "self",
                viewer.equals(rs.getObject("id", UUID.class)),
                "eligible",
                rs.getBoolean("enabled")
                    && rs.getString("approval_status").equals("APPROVED")
                    && rs.getString("state").equals("APPROVED")),
        team.id());
  }

  public void teamInvite(UUID id, String hash) {
    db.update("UPDATE league_teams SET token_hash=? WHERE id=?", hash, id);
  }

  public boolean teamInvitable(UUID id) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM league_teams WHERE id=? AND token_hash IS NOT NULL",
            Integer.class,
            id)
        > 0;
  }

  public void leaveTeam(LeagueTeam team, UUID owner) {
    db.update(
        "DELETE FROM league_team_members WHERE league_id=? AND owner_id=?", team.leagueId(), owner);
    if (team.captainId().equals(owner)) db.update("DELETE FROM league_teams WHERE id=?", team.id());
  }

  public void freeze(UUID id) {
    db.update(
        "UPDATE league_teams SET frozen_at=?,token_hash=NULL WHERE id=? AND frozen_at IS NULL",
        Timestamp.from(Instant.now()),
        id);
  }

  public int teamSubmissions(UUID id) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM league_submissions WHERE team_id=?", Integer.class, id);
  }

  public boolean teamEligible(UUID id) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM league_team_members m JOIN league_participants p ON"
                + " p.league_id=m.league_id AND p.owner_id=m.owner_id JOIN accounts a ON"
                + " a.id=m.owner_id WHERE m.team_id=? AND (p.state<>'APPROVED' OR a.enabled=false"
                + " OR a.approval_status<>'APPROVED' OR a.role<>'MEMBER' OR"
                + " a.member_type<>'PLAYER')",
            Integer.class,
            id)
        == 0;
  }
}
