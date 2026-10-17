package io.waterleague.research.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.research.service.ResearchService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class ResearchController {
  private final AccountService accounts;
  private final ResearchService research;
  private final RateLimitService rates;

  public ResearchController(AccountService a, ResearchService r, RateLimitService limits) {
    accounts = a;
    research = r;
    rates = limits;
  }

  public record Consent(@NotNull Boolean granted) {}

  @GetMapping("/api/v1/organizations")
  public Object organizations() {
    return research.organizations();
  }

  @GetMapping("/api/v1/consents")
  public Object consents(Principal p) {
    return research.consents(accounts.current(p.getName()));
  }

  @PutMapping("/api/v1/consents/{id}")
  public void consent(@PathVariable UUID id, @Valid @RequestBody Consent dto, Principal p) {
    research.consent(accounts.current(p.getName()), id, dto.granted());
  }

  @GetMapping("/api/v1/research/strategies")
  public Object list(Principal p, @RequestParam(required = false) String modelHash) {
    return research.list(accounts.current(p.getName()), modelHash);
  }

  @GetMapping("/api/v1/research/strategies/{id}")
  public Object detail(@PathVariable UUID id, Principal p) {
    return research.detail(accounts.current(p.getName()), id);
  }

  @GetMapping("/api/v1/research/strategies/{id}/bundle")
  public ResponseEntity<byte[]> export(@PathVariable UUID id, Principal p)
      throws java.io.IOException {
    return bundle(id, p, true);
  }

  @GetMapping("/api/v1/simulations/{id}/bundle")
  public ResponseEntity<byte[]> ownExport(@PathVariable UUID id, Principal p)
      throws java.io.IOException {
    return bundle(id, p, false);
  }

  private ResponseEntity<byte[]> bundle(UUID id, Principal p, boolean institution)
      throws java.io.IOException {
    var a = accounts.current(p.getName());
    rates.check("export:" + a.id(), 20, 3600);
    return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=waterleague-" + id + ".zip")
        .cacheControl(CacheControl.noStore())
        .contentType(MediaType.parseMediaType("application/zip"))
        .body(research.bundle(a, id, institution));
  }
}
