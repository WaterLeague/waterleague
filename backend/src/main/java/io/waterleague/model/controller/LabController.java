package io.waterleague.model.controller;

import io.waterleague.model.service.LabModelService;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
public class LabController {
  private final LabModelService model;

  public LabController(LabModelService m) {
    model = m;
  }

  @GetMapping("/api/v1/lab")
  public Map<String, Object> lab(@RequestParam(required = false) String modelHash) {
    return model.view(modelHash);
  }

  @GetMapping("/api/v1/lab/catalog")
  public Object catalog() {
    return model.catalog();
  }
}
