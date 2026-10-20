package io.waterleague.infrastructure.controller;

import io.waterleague.infrastructure.repository.InfrastructureRepository;
import io.waterleague.infrastructure.service.InfrastructureService;
import io.waterleague.infrastructure.view.InfrastructureView;
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/infrastructure")
public class InfrastructureController {
  private final InfrastructureService service;

  public InfrastructureController(InfrastructureService service) {
    this.service = service;
  }

  @GetMapping("/seoul-native-infrastructure-20261020-v1")
  public ResponseEntity<InfrastructureView> catalog() {
    return ResponseEntity.ok()
        .eTag(InfrastructureRepository.SHA256)
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable())
        .body(service.referenceCatalog());
  }
}
