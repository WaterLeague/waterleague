package io.waterleague.common.controller;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConnectionHealthController {
  public record ConnectionHealth(String status) {}

  @GetMapping("/api/v1/health")
  public ResponseEntity<ConnectionHealth> health() {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(new ConnectionHealth("UP"));
  }
}
