package io.waterleague.surface.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.service.SurfacePlaybackService;
import io.waterleague.surface.service.SurfacePlaybackService.Access;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class SurfacePlaybackController {
  private final AccountService accounts;
  private final RateLimitService rates;
  private final SurfacePlaybackService service;

  public SurfacePlaybackController(
      AccountService accounts, RateLimitService rates, SurfacePlaybackService service) {
    this.accounts = accounts;
    this.rates = rates;
    this.service = service;
  }

  private ResponseEntity<Object> read(
      Principal p, UUID id, Access access, SurfaceFrameRequest request) {
    var actor = accounts.current(p.getName());
    rates.check("surface-playback:" + actor.id(), 120, 60);
    var result = service.read(actor.id(), access, id, request);
    accounts.current(p.getName());
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(result);
  }

  @GetMapping("/api/v1/historical/{id}/surface/catalog")
  public ResponseEntity<Object> historical(Principal p, @PathVariable UUID id) {
    return read(p, id, Access.HISTORICAL_OWNER, null);
  }

  @GetMapping("/api/v1/installations/{id}/surface/catalog")
  public ResponseEntity<Object> latest(Principal p, @PathVariable UUID id) {
    return read(p, id, Access.LATEST_INSTALLATION, null);
  }

  @GetMapping("/api/v1/installations/{id}/surface/frame")
  public ResponseEntity<Object> latestFrame(
      Principal p, @PathVariable UUID id, @ModelAttribute SurfaceFrameRequest request) {
    return read(p, id, Access.LATEST_INSTALLATION, request);
  }

  @GetMapping("/api/v1/historical/{id}/surface/frame")
  public ResponseEntity<Object> historicalFrame(
      Principal p, @PathVariable UUID id, @ModelAttribute SurfaceFrameRequest request) {
    return read(p, id, Access.HISTORICAL_OWNER, request);
  }

  @GetMapping("/api/v1/installations/records/{id}/surface/catalog")
  public ResponseEntity<Object> own(Principal p, @PathVariable UUID id) {
    return read(p, id, Access.SHARED_OWNER, null);
  }

  @GetMapping("/api/v1/installations/records/{id}/surface/frame")
  public ResponseEntity<Object> ownFrame(
      Principal p, @PathVariable UUID id, @ModelAttribute SurfaceFrameRequest request) {
    return read(p, id, Access.SHARED_OWNER, request);
  }

  @GetMapping("/api/v1/research/installations/{id}/surface/catalog")
  public ResponseEntity<Object> research(Principal p, @PathVariable UUID id) {
    return read(p, id, Access.CONSENTED_ORGANIZATION, null);
  }

  @GetMapping("/api/v1/research/installations/{id}/surface/frame")
  public ResponseEntity<Object> researchFrame(
      Principal p, @PathVariable UUID id, @ModelAttribute SurfaceFrameRequest request) {
    return read(p, id, Access.CONSENTED_ORGANIZATION, request);
  }
}
