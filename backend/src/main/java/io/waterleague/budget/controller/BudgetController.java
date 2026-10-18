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

  public BudgetController(BudgetService service, AccountService accounts) {
    this.service = service;
    this.accounts = accounts;
  }

  @GetMapping
  public ResponseEntity<BudgetView> view(Principal principal) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.view(principal == null ? null : accounts.current(principal.getName()).id()));
  }

  @GetMapping("/ledger")
  public ResponseEntity<BudgetLedgerView> history(
      Principal principal, @RequestParam(required = false) Long beforeId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.history(accounts.current(principal.getName()).id(), beforeId));
  }
}
