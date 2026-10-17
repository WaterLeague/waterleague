package io.waterleague.utilization.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.research.service.ResearchService;
import io.waterleague.utilization.dto.*;
import io.waterleague.utilization.service.UtilizationService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class UtilizationController {
  private final AccountService accounts;
  private final UtilizationService service;
  private final ResearchService research;
  private final RateLimitService rates;

  public UtilizationController(
      AccountService accounts,
      UtilizationService service,
      ResearchService research,
      RateLimitService rates) {
    this.accounts = accounts;
    this.service = service;
    this.research = research;
    this.rates = rates;
  }

  @GetMapping("/api/v1/utilization/requests")
  public Object mine(Principal p, @RequestParam(required = false) UUID after) {
    return service.list(accounts.current(p.getName()), false, after);
  }

  @GetMapping("/api/v1/institution/utilization/requests")
  public Object institution(Principal p, @RequestParam(required = false) UUID after) {
    return service.list(accounts.current(p.getName()), true, after);
  }

  @GetMapping("/api/v1/utilization/requests/{id}")
  public Object detail(Principal p, @PathVariable UUID id) {
    return service.detail(accounts.current(p.getName()), id);
  }

  @PostMapping("/api/v1/institution/utilization/requests")
  @ResponseStatus(HttpStatus.CREATED)
  public Object create(Principal p, @Valid @RequestBody CreateUtilizationRequest dto) {
    var a = accounts.current(p.getName());
    rates.check("application-request:" + a.id(), 20, 3600);
    return service.create(a, dto);
  }

  @PostMapping("/api/v1/utilization/requests/{id}/decisions")
  public Object decide(
      Principal p, @PathVariable UUID id, @Valid @RequestBody UtilizationDecisionRequest dto) {
    var a = accounts.current(p.getName());
    rates.check("application-decision:" + a.id(), 100, 3600);
    return service.decide(a, id, dto);
  }

  @GetMapping("/api/v1/institution/utilization/requests/{id}/bundle")
  public ResponseEntity<byte[]> bundle(Principal p, @PathVariable UUID id)
      throws java.io.IOException {
    var a = accounts.current(p.getName());
    rates.check("export:" + a.id(), 20, 3600);
    return ResponseEntity.ok()
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-application-" + id + ".zip")
        .cacheControl(CacheControl.noStore())
        .contentType(MediaType.parseMediaType("application/zip"))
        .body(research.applicationBundle(a, id));
  }

  @PostMapping("/api/v1/research/strategies/{jobId}/reviews")
  @ResponseStatus(HttpStatus.CREATED)
  public Object addReview(
      Principal p, @PathVariable UUID jobId, @Valid @RequestBody CreateStrategyReviewRequest dto) {
    var a = accounts.current(p.getName());
    rates.check("strategy-review:" + a.id(), 60, 3600);
    return service.addReview(a, jobId, dto);
  }

  @GetMapping("/api/v1/research/strategies/{jobId}/reviews")
  public Object reviews(
      Principal p, @PathVariable UUID jobId, @RequestParam(required = false) UUID after) {
    return service.reviews(accounts.current(p.getName()), jobId, after);
  }

  @GetMapping("/api/v1/utilization/reviews")
  public Object ownReviews(Principal p, @RequestParam(required = false) UUID after) {
    return service.reviews(accounts.current(p.getName()), null, after);
  }
}
