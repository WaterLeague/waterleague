package io.waterleague.facility.controller;

import io.waterleague.facility.service.FacilityService;
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tools.jackson.databind.JsonNode;

@RestController
@RequestMapping("/api/v1/facilities")
public class FacilityController {
  private final FacilityService service;

  public FacilityController(FacilityService service) {
    this.service = service;
  }

  @GetMapping("/epa-designs-v1")
  public ResponseEntity<JsonNode> previous() {
    return response(true);
  }

  @GetMapping("/epa-designs-v2")
  public ResponseEntity<JsonNode> catalog() {
    return response(false);
  }

  @GetMapping("/epa-designs-v3")
  public ResponseEntity<JsonNode> v3() {
    return ResponseEntity.ok()
        .eTag(service.v3Digest())
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable())
        .body(service.v3());
  }

  @GetMapping("/epa-designs-v4")
  public ResponseEntity<JsonNode> latest() {
    return ResponseEntity.ok()
        .eTag(service.latestDigest())
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable())
        .body(service.latest());
  }

  private ResponseEntity<JsonNode> response(boolean previous) {
    return ResponseEntity.ok()
        .eTag(service.digest(previous))
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable())
        .body(service.catalog(previous));
  }
}
