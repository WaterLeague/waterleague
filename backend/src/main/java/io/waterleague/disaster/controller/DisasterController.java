package io.waterleague.disaster.controller;

import io.waterleague.disaster.service.DisasterService;
import io.waterleague.disaster.view.DisasterView;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/disasters")
public class DisasterController {
  private final DisasterService service;

  public DisasterController(DisasterService service) {
    this.service = service;
  }

  @GetMapping
  public DisasterView catalog() {
    return service.catalog();
  }
}
