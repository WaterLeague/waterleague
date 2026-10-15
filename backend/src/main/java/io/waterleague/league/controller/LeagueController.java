package io.waterleague.league.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.league.dto.LeagueDraftRequest;
import io.waterleague.league.service.LeagueService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
public class LeagueController {
  private final AccountService accounts;
  private final LeagueService leagues;
  private final RateLimitService rates;

  public LeagueController(AccountService a, LeagueService l, RateLimitService r) {
    accounts = a;
    leagues = l;
    rates = r;
  }

  public record Publish(
      @Min(1) int revision, @NotNull @Pattern(regexp = "[a-f0-9]{64}") String rulesHash) {}

  public record Cancel(@NotBlank @Size(max = 500) String reason) {}

  public record Submit(
      @NotNull UUID jobId, @NotNull @Pattern(regexp = "[a-f0-9]{64}") String rulesHash) {}

  @GetMapping("/api/v1/leagues")
  public Object list() {
    return leagues.list();
  }

  @GetMapping("/api/v1/leagues/{id}")
  public Object detail(@PathVariable UUID id, Principal p) {
    return leagues.detail(id, p == null ? null : accounts.current(p.getName()));
  }

  @GetMapping("/api/v1/leagues/{id}/mine")
  public Object mine(@PathVariable UUID id, Principal p) {
    return leagues.mine(accounts.current(p.getName()), id);
  }

  @PostMapping("/api/v1/leagues/{id}/submissions")
  public Object submit(@PathVariable UUID id, @Valid @RequestBody Submit d, Principal p) {
    var a = accounts.current(p.getName());
    rates.check("league-submit:" + a.id(), 60, 3600);
    return leagues.submit(a, id, d.jobId(), d.rulesHash());
  }

  @GetMapping("/api/v1/institution/leagues")
  public Object managed(Principal p) {
    return leagues.managedList(accounts.current(p.getName()));
  }

  @PostMapping("/api/v1/institution/leagues")
  public Object create(@Valid @RequestBody LeagueDraftRequest d, Principal p) {
    var a = accounts.current(p.getName());
    rates.check("league-create:" + a.id(), 10, 3600);
    return leagues.create(a, d);
  }

  @PutMapping("/api/v1/institution/leagues/{id}")
  public Object update(
      @PathVariable UUID id, @Valid @RequestBody LeagueDraftRequest d, Principal p) {
    return leagues.update(accounts.current(p.getName()), id, d);
  }

  @PostMapping("/api/v1/institution/leagues/{id}/publish")
  public Object publish(@PathVariable UUID id, @Valid @RequestBody Publish d, Principal p) {
    return leagues.publish(accounts.current(p.getName()), id, d.revision(), d.rulesHash());
  }

  @PostMapping("/api/v1/institution/leagues/{id}/cancel")
  public Object cancel(@PathVariable UUID id, @Valid @RequestBody Cancel d, Principal p) {
    return leagues.cancel(accounts.current(p.getName()), id, d.reason());
  }
}
