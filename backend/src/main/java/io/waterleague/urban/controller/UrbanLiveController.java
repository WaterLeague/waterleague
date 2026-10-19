package io.waterleague.urban.controller;

import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.urban.service.UrbanLiveService;
import io.waterleague.urban.view.UrbanLiveView;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/urban")
public class UrbanLiveController {
  private final UrbanLiveService urban;
  private final RateLimitService rates;
  private final JsonService json;

  public UrbanLiveController(UrbanLiveService urban, RateLimitService rates, JsonService json) {
    this.urban = urban;
    this.rates = rates;
    this.json = json;
  }

  @GetMapping("/live")
  public ResponseEntity<UrbanLiveView> latest(
      @RequestParam List<String> places, HttpServletRequest request) {
    rates.check("urban-live:" + json.hash(request.getRemoteAddr()), 30, 60);
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(urban.latest(places));
  }
}
