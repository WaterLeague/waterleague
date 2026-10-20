package io.waterleague.facility.controller;

import io.waterleague.facility.service.CisternSpecificationService;
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CisternSpecificationController {
  private final CisternSpecificationService specifications;

  public CisternSpecificationController(CisternSpecificationService specifications) {
    this.specifications = specifications;
  }

  @GetMapping("/api/v1/facilities/cistern-specifications-v1")
  public ResponseEntity<String> catalog() {
    return ResponseEntity.ok()
        .eTag(specifications.hash())
        .contentType(MediaType.APPLICATION_JSON)
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable())
        .body(specifications.catalog());
  }
}
