package io.waterleague.rainfall.controller;

import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.rainfall.repository.ObservedGameRepository;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.web.bind.annotation.*;
import tools.jackson.databind.JsonNode;

@RestController
@ConditionalOnWebApplication
@RequestMapping("/api/v1/spatial/play/forcings")
public class ObservedGameController {
  private final ObservedGameRepository repository;
  private final RateLimitService rates;
  private final JsonService json;

  public ObservedGameController(ObservedGameRepository repository, RateLimitService rates, JsonService json) {
    this.repository = repository; this.rates = rates; this.json = json;
  }

  @GetMapping
  public Map<String, Object> catalog(HttpServletRequest request) {
    check(request);
    return Map.of("catalogSha256", ObservedGameRepository.SHA256, "catalog", repository.catalog(),
        "events", repository.events());
  }

  @GetMapping("/{modelHash}")
  public JsonNode forcing(@PathVariable String modelHash, HttpServletRequest request) {
    check(request);
    return repository.require(modelHash).model();
  }

  private void check(HttpServletRequest request) {
    rates.check("native-forcing:" + json.hash(request.getRemoteAddr()), 300, 60);
  }
}
