package io.waterleague.spatial.controller;

import io.waterleague.spatial.repository.NativePlayRepository;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import tools.jackson.databind.JsonNode;

@RestController
@ConditionalOnWebApplication
@RequestMapping("/api/v1/spatial/play")
public class NativePlayController {
  private final NativePlayRepository repository;
  private final RateLimitService rates;
  private final JsonService json;

  public NativePlayController(NativePlayRepository repository, RateLimitService rates, JsonService json) {
    this.repository = repository; this.rates = rates; this.json = json;
  }

  @GetMapping
  public Map<String, Object> catalog(HttpServletRequest request) {
    check(request);
    return Map.of("catalogSha256", repository.sha256(), "coordinateSystem", "EPSG:5186",
        "catalog", repository.metadata());
  }

  @GetMapping("/sites")
  public Map<String, Object> sites(@RequestParam double minx, @RequestParam double miny,
      @RequestParam double maxx, @RequestParam double maxy,
      @RequestParam(required = false) String districtId,
      @RequestParam(required = false) String kind,
      @RequestParam(defaultValue = "512") int limit,
      @RequestParam(defaultValue = "false") boolean includeUnsupported, HttpServletRequest request) {
    check(request);
    return Map.of("catalogSha256", repository.sha256(), "coordinateSystem", "EPSG:5186",
        "sites", repository.bounds(minx, miny, maxx, maxy, districtId, kind, limit, includeUnsupported));
  }

  @GetMapping("/sites/{districtId}/{candidateId}")
  public Map<String, Object> site(@PathVariable String districtId, @PathVariable String candidateId,
      HttpServletRequest request) {
    check(request);
    return Map.of("catalogSha256", repository.sha256(), "coordinateSystem", "EPSG:5186",
        "site", repository.require(districtId, candidateId));
  }

  private void check(HttpServletRequest request) {
    rates.check("native-spatial:" + json.hash(request.getRemoteAddr()), 300, 60);
  }
}
