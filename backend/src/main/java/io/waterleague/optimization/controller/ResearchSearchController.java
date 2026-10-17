package io.waterleague.optimization.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.optimization.dto.CreateSearchRequest;
import io.waterleague.optimization.service.ResearchSearchService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/research/searches")
public class ResearchSearchController {
  private final ResearchSearchService searches;
  private final AccountService accounts;
  private final RateLimitService rates;

  public ResearchSearchController(
      ResearchSearchService searches, AccountService accounts, RateLimitService rates) {
    this.searches = searches;
    this.accounts = accounts;
    this.rates = rates;
  }

  @PostMapping
  public Object create(Principal p, @Valid @RequestBody CreateSearchRequest request) {
    var a = accounts.current(p.getName());
    rates.check("research-search:" + a.organizationId(), 6, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(searches.create(a, request));
  }

  @GetMapping
  public Object list(Principal p) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(searches.list(accounts.current(p.getName())));
  }

  @GetMapping("/{id}")
  public Object get(Principal p, @PathVariable UUID id) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(searches.get(accounts.current(p.getName()), id));
  }

  @GetMapping("/{id}/provenance")
  public ResponseEntity<String> provenance(Principal p, @PathVariable UUID id) {
    var a = accounts.current(p.getName());
    rates.check("export:" + a.id(), 20, 3600);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .contentType(MediaType.APPLICATION_JSON)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-search-" + id + ".json")
        .body(searches.provenance(a, id));
  }

  @GetMapping("/{id}/candidates/{candidateId}/bundle")
  public ResponseEntity<byte[]> bundle(
      Principal p, @PathVariable UUID id, @PathVariable UUID candidateId) {
    var a = accounts.current(p.getName());
    rates.check("export:" + a.id(), 20, 3600);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .contentType(MediaType.parseMediaType("application/zip"))
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-search-" + id + "-" + candidateId + ".zip")
        .body(searches.bundle(a, id, candidateId));
  }
}
