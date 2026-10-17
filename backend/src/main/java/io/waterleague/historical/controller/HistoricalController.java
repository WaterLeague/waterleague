package io.waterleague.historical.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.historical.dto.HistoricalRequest;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.historical.view.HistoricalView;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/historical")
public class HistoricalController {
  private final AccountService accounts;
  private final HistoricalService service;
  private final io.waterleague.historical.service.HistoricalArtifactService artifacts;
  private final io.waterleague.common.security.RateLimitService rates;

  public HistoricalController(
      AccountService accounts,
      HistoricalService service,
      io.waterleague.historical.service.HistoricalArtifactService artifacts,
      io.waterleague.common.security.RateLimitService rates) {
    this.accounts = accounts;
    this.service = service;
    this.artifacts = artifacts;
    this.rates = rates;
  }

  @GetMapping
  public ResponseEntity<List<HistoricalView>> list(Principal p) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.list(accounts.current(p.getName()).id()));
  }

  @GetMapping("/{id}")
  public ResponseEntity<HistoricalView> get(Principal p, @PathVariable UUID id) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.view(service.require(accounts.current(p.getName()).id(), id)));
  }

  @PostMapping
  public ResponseEntity<HistoricalView> create(
      Principal p, @Valid @RequestBody HistoricalRequest dto) {
    rates.check("historical:" + accounts.current(p.getName()).id(), 40, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(service.create(accounts.current(p.getName()).id(), dto));
  }

  @GetMapping("/{id}/bundle")
  public ResponseEntity<byte[]> bundle(Principal p, @PathVariable UUID id) {
    var owner = accounts.current(p.getName()).id();
    rates.check("historical-bundle:" + owner, 20, 3600);
    var value = artifacts.bundle(service.require(owner, id));
    accounts.current(p.getName());
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-historical-" + id + ".zip")
        .contentType(MediaType.parseMediaType("application/zip"))
        .body(value);
  }
}
