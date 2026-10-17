package io.waterleague.comparison.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.comparison.dto.CreateComparisonRequest;
import io.waterleague.comparison.service.ComparisonService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/comparisons")
public class ComparisonController {
  private final AccountService accounts;
  private final ComparisonService comparisons;
  private final RateLimitService rates;

  public ComparisonController(AccountService a, ComparisonService c, RateLimitService r) {
    accounts = a;
    comparisons = c;
    rates = r;
  }

  @GetMapping
  public Object list(Principal p) {
    return comparisons.list(accounts.current(p.getName()).id());
  }

  @GetMapping("/{id}")
  public Object get(@PathVariable UUID id, Principal p) {
    return comparisons.get(id, accounts.current(p.getName()).id());
  }

  @PostMapping
  @ResponseStatus(HttpStatus.ACCEPTED)
  public Object create(@Valid @RequestBody CreateComparisonRequest dto, Principal p) {
    var owner = accounts.current(p.getName()).id();
    for (int i = 0; i < dto.modelHashes().size(); i++) rates.check("run:" + owner, 40, 3600);
    return comparisons.create(owner, dto);
  }
}
