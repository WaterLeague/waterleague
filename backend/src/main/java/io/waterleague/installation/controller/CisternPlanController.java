package io.waterleague.installation.controller;

import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.installation.dto.CisternPlanRequest;
import io.waterleague.installation.service.CisternPlanService;
import io.waterleague.installation.view.CisternPlanView;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/installations/cistern-plans")
public class CisternPlanController {
  private final CisternPlanService service;
  private final RateLimitService rates;
  private final JsonService json;

  public CisternPlanController(
      CisternPlanService service, RateLimitService rates, JsonService json) {
    this.service = service;
    this.rates = rates;
    this.json = json;
  }

  @GetMapping
  public List<CisternPlanView> list(Principal p) {
    return service.list(p.getName());
  }

  @PostMapping
  public CisternPlanView save(Principal p, @Valid @RequestBody CisternPlanRequest request) {
    rates.check("cistern-plan:" + json.hash(p.getName()), 30, 60);
    return service.save(p.getName(), request);
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void remove(Principal p, @PathVariable UUID id) {
    service.remove(p.getName(), id);
  }
}
