package io.waterleague.historical.controller;

import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.historical.dto.GuestHistoricalRequest;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.historical.view.HistoricalView;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/guest-historical")
public class GuestHistoricalController {
  private final HistoricalService service;
  private final RateLimitService rates;
  private final JsonService json;

  public GuestHistoricalController(
      HistoricalService service, RateLimitService rates, JsonService json) {
    this.service = service;
    this.rates = rates;
    this.json = json;
  }

  private String guest(HttpServletRequest request) {
    // 클라이언트가 소유자를 지정할 수 없으며 세션 만료 후 이전 결과에 접근하지 못한다.
    return json.hash("historical-guest-v1:" + request.getSession().getId());
  }

  @GetMapping
  public ResponseEntity<List<HistoricalView>> list(HttpServletRequest request) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.guestList(guest(request)));
  }

  @GetMapping("/{id}")
  public ResponseEntity<HistoricalView> get(HttpServletRequest request, @PathVariable UUID id) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.guestGet(guest(request), id));
  }

  @PostMapping
  public ResponseEntity<HistoricalView> create(
      HttpServletRequest request, @Valid @RequestBody GuestHistoricalRequest dto) {
    String guest = guest(request);
    rates.check("guest-historical:" + guest, 40, 3600);
    rates.check("guest-historical-network:" + json.hash(request.getRemoteAddr()), 80, 3600);
    rates.check("guest-historical-global", 400, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(service.createGuest(guest, dto));
  }
}
