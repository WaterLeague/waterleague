package io.waterleague.physics.controller;

import io.waterleague.physics.service.PhysicsService;
import io.waterleague.physics.view.PhysicsView;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/installations")
public class PhysicsController {
  private final PhysicsService service;

  public PhysicsController(PhysicsService service) {
    this.service = service;
  }

  @GetMapping("/{id}/physics")
  public ResponseEntity<PhysicsView> latest(@PathVariable UUID id) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.latest(id));
  }
}
