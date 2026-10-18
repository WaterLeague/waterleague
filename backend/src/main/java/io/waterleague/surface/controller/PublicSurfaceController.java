package io.waterleague.surface.controller;

import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.service.PublicSurfaceService;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/surface/current")
public class PublicSurfaceController {
  private final PublicSurfaceService service;
  private final io.waterleague.common.security.RateLimitService rates;
  private final io.waterleague.common.service.JsonService json;

  public PublicSurfaceController(
      PublicSurfaceService service,
      io.waterleague.common.security.RateLimitService rates,
      io.waterleague.common.service.JsonService json) {
    this.service = service;
    this.rates = rates;
    this.json = json;
  }

  private void limit(jakarta.servlet.http.HttpServletRequest request) {
    rates.check("public-surface:" + json.hash(request.getRemoteAddr()), 240, 60);
  }

  @GetMapping
  public ResponseEntity<?> current(
      @ModelAttribute SurfaceFrameRequest request, jakarta.servlet.http.HttpServletRequest http) {
    limit(http);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.current(request, Instant.now()));
  }

  @GetMapping("/{id}/frame")
  public ResponseEntity<?> frame(
      @PathVariable UUID id,
      @ModelAttribute SurfaceFrameRequest request,
      jakarta.servlet.http.HttpServletRequest http) {
    limit(http);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.frame(id, request, Instant.now()));
  }
}
