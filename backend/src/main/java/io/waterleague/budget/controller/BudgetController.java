package io.waterleague.budget.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.budget.view.BudgetView;
import java.security.Principal;
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
  public BudgetView view(Principal principal) {
    return service.view(principal == null ? null : accounts.current(principal.getName()).id());
  }
}
