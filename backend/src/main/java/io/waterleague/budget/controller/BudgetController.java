package io.waterleague.budget.controller;

import io.waterleague.budget.service.BudgetService;
import io.waterleague.budget.view.BudgetView;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/budget")
public class BudgetController {
  private final BudgetService service;

  public BudgetController(BudgetService service) {
    this.service = service;
  }

  @GetMapping
  public BudgetView view() {
    return service.view();
  }
}
