package io.waterleague.strategy.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.strategy.dto.SaveStrategyRequest;
import io.waterleague.strategy.service.StrategyService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/strategies")
public class StrategyController {
  private final AccountService accounts;
  private final StrategyService strategies;
  private final RateLimitService rates;

  public StrategyController(AccountService a, StrategyService s, RateLimitService r) {
    accounts = a;
    strategies = s;
    rates = r;
  }

  @GetMapping
  public Object list(Principal p) {
    return strategies.list(accounts.current(p.getName()).id());
  }

  @GetMapping("/{id}")
  public Object get(@PathVariable UUID id, Principal p) {
    return strategies.get(id, accounts.current(p.getName()).id());
  }

  @PostMapping
  public Object create(@Valid @RequestBody SaveStrategyRequest dto, Principal p) {
    var id = accounts.current(p.getName()).id();
    rates.check("save:" + id, 120, 3600);
    return strategies.create(id, dto);
  }

  @PostMapping("/{id}/versions")
  public Object save(
      @PathVariable UUID id, @Valid @RequestBody SaveStrategyRequest dto, Principal p) {
    var owner = accounts.current(p.getName()).id();
    rates.check("save:" + owner, 120, 3600);
    return strategies.save(id, owner, dto);
  }
}
