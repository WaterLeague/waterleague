package io.waterleague.weekly.controller;

import io.waterleague.weekly.service.WeeklyService;
import io.waterleague.weekly.view.WeeklyView;
import java.security.Principal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/weekly")
public class WeeklyController {
  private final WeeklyService service;

  public WeeklyController(WeeklyService service) {
    this.service = service;
  }

  @GetMapping
  public WeeklyView dashboard(Principal principal) {
    return service.dashboard(principal == null ? null : principal.getName());
  }
}
