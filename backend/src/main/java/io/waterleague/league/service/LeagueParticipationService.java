package io.waterleague.league.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.league.entity.*;
import io.waterleague.league.exception.LeagueException;
import io.waterleague.league.mapper.LeagueMapper;
import io.waterleague.league.repository.*;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.research.repository.ResearchRepository;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LeagueParticipationService {
  private final LeagueRepository leagues;
  private final LeagueParticipationRepository people;
  private final ResearchRepository research;
  private final AccountRepository accounts;
  private final JsonService json;
  private final LeagueMapper mapper;
  private final LabModelRepository models;
  private final SecureRandom random = new SecureRandom();

  public LeagueParticipationService(
      LeagueRepository l,
      LeagueParticipationRepository p,
      ResearchRepository r,
      AccountRepository a,
      JsonService j,
      LeagueMapper m,
      LabModelRepository models) {
    leagues = l;
    people = p;
    research = r;
    accounts = a;
    json = j;
    mapper = m;
    this.models = models;
  }

  private void missing() {
    throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }

  private void conflict() {
    throw new LeagueException(ErrorCode.LEAGUE_PARTICIPATION_CONFLICT);
  }

  public LeagueParticipationRules rules(League l) {
    return json.read(l.rules(), LeagueRules.class).participation();
  }

  public boolean organizer(League l, Account a) {
    return a != null
        && a.usable()
        && a.organizationMember()
        && l.organizationId().equals(a.organizationId())
        && research.approved(l.organizationId());
  }

  public boolean approved(UUID league, UUID owner) {
    return people.get(league, owner).map(p -> p.state().equals("APPROVED")).orElse(false);
  }

  public void requireView(League l, Account a) {
    if (l.state().equals("DRAFT") || !research.approved(l.organizationId())) missing();
    var r = rules(l);
    if (r == null || r.access() == LeagueParticipationRules.Access.PUBLIC || organizer(l, a))
      return;
    if (a != null
        && a.usable()
        && people
            .get(l.id(), a.id())
            .map(p -> Set.of("PENDING", "APPROVED").contains(p.state()))
            .orElse(false)) return;
    missing();
  }

  public boolean boardVisible(League l, Account a) {
    var r = rules(l);
    return r == null
        || r.access() == LeagueParticipationRules.Access.PUBLIC
        || organizer(l, a)
        || (a != null && a.usable() && approved(l.id(), a.id()));
  }

  public Account lockAccount(Account a) {
    // 참가 변경과 제출의 잠금 순서를 회원→리그로 통일한다.
    research.ownerLock(a.id());
    var fresh =
        accounts.byId(a.id()).orElseThrow(() -> new DomainException(ErrorCode.ACCESS_DENIED));
    if (!fresh.usable()) throw new DomainException(ErrorCode.ACCESS_DENIED);
    return fresh;
  }

  public Account lockPlayer(Account a) {
    var fresh = lockAccount(a);
    player(fresh);
    return fresh;
  }

  private void player(Account a) {
    if (!a.usable() || !a.role().equals("MEMBER") || !a.memberType().equals("PLAYER"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  private League get(UUID id, boolean lock) {
    var l =
        leagues.get(id, lock).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (l.state().equals("DRAFT") || !research.approved(l.organizationId())) missing();
    if (!json.hash(l.rules()).equals(l.rulesHash()))
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    return l;
  }

  private void recruiting(League l) {
    if (!l.state().equals("PUBLISHED") || !Instant.now().isBefore(l.closesAt()))
      throw new LeagueException(ErrorCode.LEAGUE_CLOSED);
    if (rules(l) == null) conflict();
  }

  private League managed(Account a, UUID id) {
    if (!a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    var l = get(id, true);
    if (!organizer(l, a)) missing();
    return l;
  }

  private String token() {
    byte[] bytes = new byte[32];
    random.nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }

  private String digest(String purpose, String code) {
    return json.hash("waterleague:" + purpose + ":" + code);
  }

  private void inviteRequired(League l, String code) {
    if (code == null
        || !people.invited(digest("league", code), Instant.now()).map(l.id()::equals).orElse(false))
      missing();
  }

  public Object applications(Account a) {
    player(a);
    return people.applications(a.id());
  }

  public Object joined(Account a) {
    player(a);
    return people.joined(a.id()).stream()
        .map(id -> leagues.get(id, false).orElseThrow())
        .map(l -> mapper.view(l, models.contains(l.modelHash()), Instant.now()))
        .toList();
  }

  public Object preview(Account a, String code) {
    player(a);
    UUID id =
        people
            .invited(digest("league", code), Instant.now())
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    var l = get(id, false);
    recruiting(l);
    return mapper.view(l, models.contains(l.modelHash()), Instant.now());
  }

  public Object self(Account a, UUID id) {
    player(a);
    var l = get(id, false);
    var p = people.get(id, a.id());
    if (p.isEmpty()) requireView(l, a);
    var data = new LinkedHashMap<String, Object>();
    data.put("participant", p.orElse(null));
    data.put("events", people.events(id, a.id()));
    var team = people.ownTeam(id, a.id());
    data.put("team", team.map(t -> teamView(t, a, l)).orElse(null));
    data.put(
        "submissionCount",
        team.map(t -> people.teamSubmissions(t.id())).orElseGet(() -> leagues.count(id, a.id())));
    return data;
  }

  @Transactional
  public Object join(Account a, UUID id, String hash, String code) {
    a = lockAccount(a);
    player(a);
    var l = get(id, true);
    recruiting(l);
    if (!l.rulesHash().equals(hash)) throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    var previous = people.get(id, a.id());
    if (previous.isPresent() && Set.of("PENDING", "APPROVED").contains(previous.get().state()))
      return self(a, id);
    if (rules(l).access() == LeagueParticipationRules.Access.INVITE) inviteRequired(l, code);
    if (previous.isEmpty() && people.size(id) >= 10000)
      throw new DomainException(ErrorCode.RATE_LIMITED);
    people.change(
        id,
        a.id(),
        a.id(),
        rules(l).admission() == LeagueParticipationRules.Admission.OPEN
                && previous.map(p -> !p.reviewRequired()).orElse(true)
            ? "APPROVED"
            : "PENDING",
        hash,
        "");
    research.audit(a.id(), "LEAGUE_JOINED", id);
    return self(a, id);
  }

  @Transactional
  public Object withdraw(Account a, UUID id, int revision) {
    a = lockAccount(a);
    player(a);
    get(id, true);
    var p =
        people.get(id, a.id()).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (p.revision() != revision || !Set.of("PENDING", "APPROVED").contains(p.state())) conflict();
    people.change(id, a.id(), a.id(), "WITHDRAWN", p.rulesHash(), "");
    research.audit(a.id(), "LEAGUE_WITHDRAWN", id);
    return self(a, id);
  }

  @Transactional(readOnly = true)
  public Object participants(Account a, UUID id, UUID after) {
    var l = get(id, false);
    if (!organizer(l, a)) missing();
    var rows = people.page(id, after);
    boolean more = rows.size() > 100;
    var out = new LinkedHashMap<String, Object>();
    out.put("items", rows.stream().limit(100).toList());
    out.put("nextCursor", more ? rows.get(99).ownerId() : null);
    return out;
  }

  public Object events(Account a, UUID id, UUID owner) {
    var l = get(id, false);
    if (!organizer(l, a)) missing();
    if (people.get(id, owner).isEmpty()) missing();
    return people.events(id, owner);
  }

  @Transactional
  public Object decide(
      Account a, UUID id, UUID owner, int revision, String decision, String reason) {
    a = lockAccount(a);
    var l = managed(a, id);
    recruiting(l);
    var p =
        people.get(id, owner).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (p.revision() != revision
        || !(p.state().equals("PENDING")
            || (p.state().equals("APPROVED") && decision.equals("REJECTED")))) conflict();
    if (reason.strip().isEmpty()) throw new DomainException(ErrorCode.REQUEST_INVALID);
    people.change(id, owner, a.id(), decision, p.rulesHash(), reason.strip());
    people.reviewRequired(id, owner, decision.equals("REJECTED"));
    research.audit(a.id(), "LEAGUE_PARTICIPANT_REVIEWED", id);
    return people.get(id, owner).orElseThrow();
  }

  public Object invitationStatus(Account a, UUID id) {
    var l = get(id, false);
    if (!organizer(l, a)) missing();
    return Map.of(
        "active", l.state().equals("PUBLISHED") && people.hasInvite(id), "expiresAt", l.closesAt());
  }

  @Transactional
  public Object invitation(Account a, UUID id, boolean revoke) {
    a = lockAccount(a);
    var l = managed(a, id);
    recruiting(l);
    if (rules(l).access() != LeagueParticipationRules.Access.INVITE) conflict();
    String code = revoke ? null : token();
    people.invite(id, code == null ? null : digest("league", code), l.closesAt());
    research.audit(a.id(), revoke ? "LEAGUE_INVITE_REVOKED" : "LEAGUE_INVITE_ROTATED", id);
    return code == null ? Map.of("active", false) : Map.of("code", code, "expiresAt", l.closesAt());
  }

  private League teamLeague(Account a, UUID id) {
    player(a);
    var l = get(id, true);
    recruiting(l);
    if (!approved(id, a.id()) || !rules(l).team()) conflict();
    return l;
  }

  private Object teamView(LeagueTeam t, Account a, League l) {
    var view = new LinkedHashMap<String, Object>();
    view.put("id", t.id());
    view.put("name", t.name());
    view.put("captain", t.captainId().equals(a.id()));
    view.put("frozenAt", t.frozenAt());
    view.put("members", people.roster(t, a.id()));
    view.put("submissionCount", people.teamSubmissions(t.id()));
    view.put("eligible", people.teamEligible(t.id()));
    view.put(
        "invitationActive",
        l.state().equals("PUBLISHED")
            && Instant.now().isBefore(l.closesAt())
            && people.teamInvitable(t.id()));
    return view;
  }

  @Transactional
  public Object createTeam(Account a, UUID id, String name) {
    a = lockAccount(a);
    var l = teamLeague(a, id);
    name = name.strip();
    if (name.isEmpty() || name.codePoints().anyMatch(Character::isISOControl))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    if (people.ownTeam(id, a.id()).isPresent() || people.nameExists(id, name)) conflict();
    String code = token();
    var t = people.createTeam(id, a.id(), name, digest("team", code));
    research.audit(a.id(), "LEAGUE_TEAM_CREATED", id);
    return Map.of("team", teamView(t, a, l), "code", code);
  }

  @Transactional
  public Object previewTeam(Account a, UUID id, String code) {
    a = lockAccount(a);
    var l = teamLeague(a, id);
    var t =
        people
            .invitedTeam(id, digest("team", code))
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (t.frozenAt() != null) conflict();
    return Map.of(
        "id",
        t.id(),
        "name",
        t.name(),
        "memberCount",
        people.teamSize(t.id()),
        "teamSizeLimit",
        rules(l).teamSizeLimit(),
        "rulesHash",
        l.rulesHash());
  }

  @Transactional
  public Object joinTeam(Account a, UUID id, String code, UUID expectedTeam, String hash) {
    a = lockAccount(a);
    var l = teamLeague(a, id);
    if (!l.rulesHash().equals(hash)) throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    var t =
        people
            .invitedTeam(id, digest("team", code))
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!t.id().equals(expectedTeam)) missing();
    var current = people.ownTeam(id, a.id());
    if (current.isPresent() && current.get().id().equals(t.id())) return self(a, id);
    if (current.isPresent()
        || t.frozenAt() != null
        || people.teamSize(t.id()) >= rules(l).teamSizeLimit()) conflict();
    people.joinTeam(id, t.id(), a.id());
    research.audit(a.id(), "LEAGUE_TEAM_JOINED", id);
    return self(a, id);
  }

  @Transactional
  public Object leaveTeam(Account a, UUID id) {
    a = lockAccount(a);
    player(a);
    var l = get(id, true);
    recruiting(l);
    var t =
        people
            .ownTeam(id, a.id())
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (t.frozenAt() != null || (t.captainId().equals(a.id()) && people.teamSize(t.id()) > 1))
      conflict();
    people.leaveTeam(t, a.id());
    research.audit(a.id(), "LEAGUE_TEAM_LEFT", id);
    return self(a, id);
  }

  @Transactional
  public Object teamInvitation(Account a, UUID id, boolean revoke) {
    a = lockAccount(a);
    var l = teamLeague(a, id);
    var t =
        people
            .ownTeam(id, a.id())
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!t.captainId().equals(a.id())) missing();
    if (t.frozenAt() != null) conflict();
    String code = revoke ? null : token();
    people.teamInvite(t.id(), code == null ? null : digest("team", code));
    research.audit(a.id(), revoke ? "TEAM_INVITE_REVOKED" : "TEAM_INVITE_ROTATED", id);
    return code == null ? Map.of("active", false) : Map.of("code", code, "expiresAt", l.closesAt());
  }

  public UUID submissionTeam(League l, Account a) {
    var r = rules(l);
    if (r == null) return null;
    if (!approved(l.id(), a.id())) conflict();
    if (!r.team()) return null;
    var team =
        people
            .ownTeam(l.id(), a.id())
            .orElseThrow(() -> new LeagueException(ErrorCode.LEAGUE_PARTICIPATION_CONFLICT));
    if (!people.teamEligible(team.id())) conflict();
    return team.id();
  }

  public int submissions(UUID league, UUID owner, UUID team) {
    return team == null ? leagues.count(league, owner) : people.teamSubmissions(team);
  }

  public void freeze(UUID team) {
    if (team != null) people.freeze(team);
  }
}
