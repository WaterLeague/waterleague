package io.waterleague.competition.controller;

import io.waterleague.account.entity.Account;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.competition.dto.CompetitionRequest;
import io.waterleague.competition.service.CompetitionService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/competitions")
public class CompetitionController {
  private final AccountService accounts;
  private final CompetitionService service;
  private final RateLimitService rates;

  public CompetitionController(
      AccountService accounts, CompetitionService service, RateLimitService rates) {
    this.accounts = accounts;
    this.service = service;
    this.rates = rates;
  }

  private Account account(Principal p) {
    return p == null ? null : accounts.current(p.getName());
  }

  public record Join(@NotNull @Pattern(regexp = "[a-f0-9]{64}") String rulesHash) {}

  public record Submission(
      @NotNull UUID jobId, @NotNull @Pattern(regexp = "[a-f0-9]{64}") String rulesHash) {}

  @GetMapping("/catalog")
  public Object catalog() {
    return service.catalog();
  }

  @GetMapping
  public Object list(Principal p, @RequestParam(defaultValue = "0") int page) {
    return service.list(account(p), page);
  }

  @GetMapping("/{id}")
  public Object detail(Principal p, @PathVariable UUID id) {
    return service.detail(account(p), id);
  }

  @PostMapping
  public Object create(Principal p, @Valid @RequestBody CompetitionRequest d) {
    var a = account(p);
    rates.check("competition-create:" + a.id(), 10, 3600);
    return service.create(a, d);
  }

  @PostMapping("/{id}/join")
  public Object join(Principal p, @PathVariable UUID id, @Valid @RequestBody Join d) {
    var a = account(p);
    rates.check("competition-join:" + a.id(), 30, 3600);
    return service.join(a, id, d.rulesHash());
  }

  @PostMapping("/{id}/cancel")
  public Object cancel(Principal p, @PathVariable UUID id) {
    return service.cancel(account(p), id);
  }

  @GetMapping("/{id}/candidates")
  public Object candidates(Principal p, @PathVariable UUID id) {
    return service.candidates(account(p), id);
  }

  @PostMapping("/{id}/submissions")
  public Object submit(Principal p, @PathVariable UUID id, @Valid @RequestBody Submission d) {
    var a = account(p);
    rates.check("competition-submit:" + a.id(), 60, 3600);
    return service.submit(a, id, d.jobId(), d.rulesHash());
  }

  @GetMapping("/{id}/results")
  public Object results(
      Principal p, @PathVariable UUID id, @RequestParam(defaultValue = "0") int page) {
    return service.results(account(p), id, page);
  }
}
