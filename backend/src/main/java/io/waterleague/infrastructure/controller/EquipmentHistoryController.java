package io.waterleague.infrastructure.controller;

import io.waterleague.common.service.JsonService;
import io.waterleague.infrastructure.service.EquipmentHistoryService;
import io.waterleague.infrastructure.view.EquipmentHistoryView;
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/infrastructure")
public class EquipmentHistoryController {
  private final EquipmentHistoryService service;
  private final JsonService json;
  public EquipmentHistoryController(EquipmentHistoryService service, JsonService json) {
    this.service = service;
    this.json = json;
  }

  @GetMapping("/equipment-history-20261018-v1")
  public ResponseEntity<EquipmentHistoryView> history(@RequestParam(required = false) String eventId) {
    var value = service.view(eventId);
    return ResponseEntity.ok().eTag(json.hash(json.write(value)))
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic().immutable()).body(value);
  }
}
