package io.waterleague.floodtrace.controller;

import io.waterleague.floodtrace.repository.FloodTraceRepository;
import io.waterleague.floodtrace.service.FloodTraceService;
import io.waterleague.floodtrace.view.FloodTraceView;
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/flood-traces/" + FloodTraceRepository.VERSION)
public class FloodTraceController {
  private final FloodTraceService service;
  public FloodTraceController(FloodTraceService service) { this.service = service; }

  private CacheControl cache() {
    return CacheControl.maxAge(Duration.ofDays(365)).cachePublic().immutable();
  }

  @GetMapping("/catalog")
  public ResponseEntity<FloodTraceView> catalog() {
    return ResponseEntity.ok().eTag(FloodTraceRepository.SHA256).cacheControl(cache())
        .body(service.catalog());
  }

  @GetMapping(value = "/{eventId}/{tileId}", produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<String> tile(@PathVariable String eventId, @PathVariable String tileId) {
    var result = service.tile(eventId, tileId);
    return ResponseEntity.ok().eTag(result.sha256()).cacheControl(cache())
        .contentType(MediaType.APPLICATION_JSON).body(result.json());
  }
}
