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
  public ResponseEntity<JsonNode> catalog() {
    return ResponseEntity.ok()
        .eTag(service.digest())
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable())
        .body(service.catalog());
  }
}
