package io.waterleague.historical.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.historical.dto.HistoricalDesignRequest;
import io.waterleague.historical.service.HistoricalDesignService;
import jakarta.validation.Valid;
import java.security.Principal;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/historical/designs")
public class HistoricalDesignController {
  private final AccountService accounts;
  private final HistoricalDesignService service;
  private final RateLimitService rates;

  public HistoricalDesignController(
      AccountService accounts, HistoricalDesignService service, RateLimitService rates) {
    this.accounts = accounts;
    this.service = service;
    this.rates = rates;
  }

  @GetMapping("/{eventId}")
  public ResponseEntity<?> get(
      Principal p,
      @PathVariable String eventId,
      @RequestParam(required = false) java.util.UUID competitionId) {
    var actor = accounts.current(p.getName());
    rates.check("historical-design-read:" + actor.id(), 120, 60);
    var value = service.get(actor.id(), eventId, competitionId);
    accounts.current(p.getName());
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value);
  }

  @GetMapping("/{eventId}/revisions/{revision}")
  public ResponseEntity<?> revision(
      Principal p,
      @PathVariable String eventId,
      @PathVariable long revision,
      @RequestParam(required = false) java.util.UUID competitionId) {
    var actor = accounts.current(p.getName());
    rates.check("historical-design-read:" + actor.id(), 120, 60);
    var value = service.revision(actor.id(), eventId, revision, competitionId);
    accounts.current(p.getName());
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value);
  }

  @PutMapping("/{eventId}")
  public ResponseEntity<?> save(
      Principal p,
      @PathVariable String eventId,
      @Valid @RequestBody HistoricalDesignRequest dto,
      @RequestParam(required = false) java.util.UUID competitionId) {
    var actor = accounts.current(p.getName());
    rates.check("historical-design:" + actor.id(), 240, 3600);
    var value = service.save(actor.id(), eventId, dto, competitionId);
    accounts.current(p.getName());
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value);
  }
}
