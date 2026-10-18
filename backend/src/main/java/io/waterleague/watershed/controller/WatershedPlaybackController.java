package io.waterleague.watershed.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.watershed.service.WatershedPlaybackService;
import io.waterleague.watershed.view.WatershedPlaybackView;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/watersheds/{id}/playback")
public class WatershedPlaybackController {
  private final AccountService accounts;
  private final WatershedPlaybackService playback;
  private final RateLimitService rates;

  public WatershedPlaybackController(
      AccountService accounts, WatershedPlaybackService playback, RateLimitService rates) {
    this.accounts = accounts;
    this.playback = playback;
    this.rates = rates;
  }

  @GetMapping
  public ResponseEntity<WatershedPlaybackView.Catalog> catalog(
      Principal principal, @PathVariable UUID id) {
    var owner = accounts.current(principal.getName()).id();
    rates.check("watershed-playback:" + owner, 240, 60);
    var result = playback.catalog(principal.getName(), id);
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(result);
  }

  @GetMapping("/frame")
  public ResponseEntity<WatershedPlaybackView.Frame> frame(
      Principal principal, @PathVariable UUID id, @RequestParam double seconds) {
    var owner = accounts.current(principal.getName()).id();
    rates.check("watershed-playback:" + owner, 240, 60);
    var result = playback.frame(principal.getName(), id, seconds);
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(result);
  }
}
