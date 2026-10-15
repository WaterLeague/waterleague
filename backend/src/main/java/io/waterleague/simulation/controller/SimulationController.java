package io.waterleague.simulation.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.simulation.dto.RunRequest;
import io.waterleague.simulation.service.SimulationService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/simulations")
public class SimulationController {
  private final AccountService accounts;
  private final SimulationService simulations;
  private final RateLimitService rates;

  public SimulationController(AccountService a, SimulationService s, RateLimitService r) {
    accounts = a;
    simulations = s;
    rates = r;
  }

  @PostMapping
  @ResponseStatus(HttpStatus.ACCEPTED)
  public Object create(@Valid @RequestBody RunRequest dto, Principal p) {
    var id = accounts.current(p.getName()).id();
    rates.check("run:" + id, 40, 3600);
    return simulations.enqueue(id, dto);
  }

  @GetMapping
  public Object list(Principal p) {
    return simulations.list(accounts.current(p.getName()).id());
  }

  @GetMapping("/{id}")
  public Object get(@PathVariable UUID id, Principal p) {
    return simulations.get(id, accounts.current(p.getName()).id());
  }
}
