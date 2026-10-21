package io.waterleague.budget.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.budget.view.BudgetLedgerView;
import io.waterleague.budget.view.BudgetView;
import java.security.Principal;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/budget")
public class BudgetController {
  private final BudgetService service;
  private final AccountService accounts;
  private final io.waterleague.competition.service.CompetitionBudgetService competitions;

  public BudgetController(
      BudgetService service,
      AccountService accounts,
      io.waterleague.competition.service.CompetitionBudgetService competitions) {
    this.service = service;
    this.accounts = accounts;
    this.competitions = competitions;
  }

  @GetMapping
  public ResponseEntity<BudgetView> view(
      Principal principal, @RequestParam(required = false) java.util.UUID competitionId) {
    var owner = principal == null ? null : accounts.current(principal.getName()).id();
    if (competitionId != null && owner == null)
      throw new io.waterleague.common.exception.DomainException(
          io.waterleague.common.exception.ErrorCode.AUTHENTICATION_REQUIRED);
    var c = competitions.require(owner, competitionId, null, null, false);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.view(owner, competitionId, competitions.policy(c)));
  }

  @GetMapping("/ledger")
  public ResponseEntity<BudgetLedgerView> history(
      Principal principal, @RequestParam(required = false) Long beforeId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.history(accounts.current(principal.getName()).id(), beforeId));
  }
}
