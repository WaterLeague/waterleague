package io.waterleague.league.controller;

import io.waterleague.account.entity.Account;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.league.dto.LeagueParticipationCommands.*;
import io.waterleague.league.service.LeagueParticipationService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class LeagueParticipationController {
  private final AccountService accounts;
  private final LeagueParticipationService participation;
  private final RateLimitService rates;

  public LeagueParticipationController(
      AccountService a, LeagueParticipationService p, RateLimitService r) {
    accounts = a;
    participation = p;
    rates = r;
  }

  private Account read(Principal p) {
    return accounts.current(p.getName());
  }

  private Account write(Principal p) {
    var a = read(p);
    rates.check("league-participation:" + a.id(), 120, 3600);
    return a;
  }

  private ResponseEntity<Object> secret(Object body) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body);
  }

  @GetMapping("/api/v1/leagues/participations")
  public Object applications(Principal p) {
    return participation.applications(read(p));
  }

  @GetMapping("/api/v1/leagues/joined")
  public Object joined(Principal p) {
    return participation.joined(read(p));
  }

  @PostMapping("/api/v1/leagues/invitations/preview")
  public Object preview(Principal p, @Valid @RequestBody Code d) {
    return secret(participation.preview(write(p), d.code()));
  }

  @GetMapping("/api/v1/leagues/{id}/participation")
  public Object self(Principal p, @PathVariable UUID id) {
    return participation.self(read(p), id);
  }

  @PostMapping("/api/v1/leagues/{id}/participation")
  public Object join(Principal p, @PathVariable UUID id, @Valid @RequestBody Join d) {
    return participation.join(write(p), id, d.rulesHash(), d.code());
  }

  @PostMapping("/api/v1/leagues/{id}/participation/withdraw")
  public Object withdraw(Principal p, @PathVariable UUID id, @Valid @RequestBody Revision d) {
    return participation.withdraw(write(p), id, d.revision());
  }

  @GetMapping("/api/v1/institution/leagues/{id}/participants")
  public Object participants(
      Principal p, @PathVariable UUID id, @RequestParam(required = false) UUID after) {
    return participation.participants(read(p), id, after);
  }

  @GetMapping("/api/v1/institution/leagues/{id}/participants/{owner}/events")
  public Object events(Principal p, @PathVariable UUID id, @PathVariable UUID owner) {
    return participation.events(read(p), id, owner);
  }

  @PostMapping("/api/v1/institution/leagues/{id}/participants/{owner}/decisions")
  public Object decision(
      Principal p,
      @PathVariable UUID id,
      @PathVariable UUID owner,
      @Valid @RequestBody Decision d) {
    return participation.decide(write(p), id, owner, d.revision(), d.state(), d.reason());
  }

  @GetMapping("/api/v1/institution/leagues/{id}/invitation")
  public Object status(Principal p, @PathVariable UUID id) {
    return participation.invitationStatus(read(p), id);
  }

  @PostMapping("/api/v1/institution/leagues/{id}/invitation")
  public Object invitation(Principal p, @PathVariable UUID id) {
    return secret(participation.invitation(write(p), id, false));
  }

  @DeleteMapping("/api/v1/institution/leagues/{id}/invitation")
  public Object revoke(Principal p, @PathVariable UUID id) {
    return participation.invitation(write(p), id, true);
  }

  @PostMapping("/api/v1/leagues/{id}/teams")
  public Object createTeam(Principal p, @PathVariable UUID id, @Valid @RequestBody Team d) {
    return secret(participation.createTeam(write(p), id, d.name()));
  }

  @PostMapping("/api/v1/leagues/{id}/teams/preview")
  public Object previewTeam(Principal p, @PathVariable UUID id, @Valid @RequestBody Code d) {
    return secret(participation.previewTeam(write(p), id, d.code()));
  }

  @PostMapping("/api/v1/leagues/{id}/teams/join")
  public Object joinTeam(Principal p, @PathVariable UUID id, @Valid @RequestBody TeamJoin d) {
    return participation.joinTeam(write(p), id, d.code(), d.teamId(), d.rulesHash());
  }

  @PostMapping("/api/v1/leagues/{id}/teams/leave")
  public Object leaveTeam(Principal p, @PathVariable UUID id) {
    return participation.leaveTeam(write(p), id);
  }

  @PostMapping("/api/v1/leagues/{id}/teams/invitation")
  public Object teamInvitation(Principal p, @PathVariable UUID id) {
    return secret(participation.teamInvitation(write(p), id, false));
  }

  @DeleteMapping("/api/v1/leagues/{id}/teams/invitation")
  public Object revokeTeam(Principal p, @PathVariable UUID id) {
    return participation.teamInvitation(write(p), id, true);
  }
}
