package io.waterleague.cost.controller;

import io.waterleague.cost.service.CostService;
import io.waterleague.cost.view.CostRecordView;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
public class CostController {
  private final CostService service;

  public CostController(CostService service) {
    this.service = service;
  }

  @GetMapping("/api/v1/installations/{id}/cost")
  public CostRecordView get(@PathVariable UUID id) {
    return service.active(id);
  }
}
