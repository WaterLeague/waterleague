package io.waterleague.rainfall.controller;

import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.rainfall.service.LiveRainfallService;
import io.waterleague.rainfall.view.LiveRainfallView;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/rainfall")
public class LiveRainfallController {
  private final LiveRainfallService rainfall;
  private final RateLimitService rates;
  private final JsonService json;

  public LiveRainfallController(
      LiveRainfallService rainfall, RateLimitService rates, JsonService json) {
    this.rainfall = rainfall;
    this.rates = rates;
    this.json = json;
  }

  @GetMapping("/live")
  public ResponseEntity<LiveRainfallView> latest(HttpServletRequest request) {
    rates.check("live-rain:" + json.hash(request.getRemoteAddr()), 30, 60);
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(rainfall.latest());
  }
}
