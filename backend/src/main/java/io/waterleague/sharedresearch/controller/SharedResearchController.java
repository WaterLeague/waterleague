package io.waterleague.sharedresearch.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.sharedresearch.dto.SharedConsentRequest;
import io.waterleague.sharedresearch.service.SharedResearchService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class SharedResearchController {
  private final SharedResearchService service;
  private final AccountService accounts;
  private final RateLimitService rates;

  public SharedResearchController(
      SharedResearchService service, AccountService accounts, RateLimitService rates) {
    this.service = service;
    this.accounts = accounts;
    this.rates = rates;
  }

  private UUID actor(Principal p) {
    return accounts.current(p.getName()).id();
  }

  @GetMapping("/api/v1/consents/shared")
  public Object consents(Principal p) {
    return service.consents(actor(p));
  }

  @PutMapping("/api/v1/consents/shared/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void consent(
      Principal p, @PathVariable UUID id, @Valid @RequestBody SharedConsentRequest dto) {
    var a = actor(p);
    rates.check("shared-consent:" + a, 60, 60);
    service.consent(a, id, dto.granted());
  }

  @GetMapping("/api/v1/installations/records")
  public Object own(Principal p, @RequestParam(required = false) LocalDate weekStart) {
    return service.list(actor(p), false, weekStart);
  }

  @GetMapping("/api/v1/research/installations")
  public Object list(Principal p, @RequestParam(required = false) LocalDate weekStart) {
    return service.list(actor(p), true, weekStart);
  }

  @GetMapping("/api/v1/installations/records/{id}")
  public Object ownDetail(Principal p, @PathVariable UUID id) {
    return detail(p, id, false);
  }

  @GetMapping("/api/v1/research/installations/{id}")
  public Object detail(Principal p, @PathVariable UUID id) {
    return detail(p, id, true);
  }

  private Object detail(Principal p, UUID id, boolean institution) {
    var a = actor(p);
    rates.check("shared-record:" + a, 60, 60);
    return service.detail(a, institution, id);
  }

  @GetMapping("/api/v1/installations/records/{id}/bundle")
  public ResponseEntity<byte[]> ownBundle(Principal p, @PathVariable UUID id) {
    return bundle(p, id, false);
  }

  @GetMapping("/api/v1/research/installations/{id}/bundle")
  public ResponseEntity<byte[]> bundle(Principal p, @PathVariable UUID id) {
    return bundle(p, id, true);
  }

  private ResponseEntity<byte[]> bundle(Principal p, UUID id, boolean institution) {
    var a = actor(p);
    rates.check("export:" + a, 20, 3600);
    return ResponseEntity.ok()
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-shared-" + id + ".zip")
        .cacheControl(CacheControl.noStore())
        .contentType(MediaType.parseMediaType("application/zip"))
        .body(service.bundle(a, institution, id));
  }
}
