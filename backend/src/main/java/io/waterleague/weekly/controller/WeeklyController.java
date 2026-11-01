package io.waterleague.weekly.controller;

import io.waterleague.weekly.service.WeeklyService;
import io.waterleague.weekly.view.WeeklyView;
import java.security.Principal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/weekly")
public class WeeklyController {
  private final WeeklyService service;
  private final io.waterleague.weekly.service.WeeklySettlementService settlement;

  public WeeklyController(
      WeeklyService service, io.waterleague.weekly.service.WeeklySettlementService settlement) {
    this.service = service;
    this.settlement = settlement;
  }

  @GetMapping("/sites/{district}/{cell}")
  public io.waterleague.weekly.view.SiteScorePage siteScores(
      @PathVariable String district,
      @PathVariable String cell,
      @RequestParam(required = false) java.util.UUID after) {
    return service.siteScores(district, cell, after);
  }

  @GetMapping
  public WeeklyView dashboard(Principal principal) {
    return settlement.dashboard(principal == null ? null : principal.getName());
  }
}
