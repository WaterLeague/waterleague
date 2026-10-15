package io.waterleague.spatial.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.spatial.service.SpatialService;
import io.waterleague.spatial.view.SpatialView;
import java.security.Principal;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/spatial")
public class SpatialController {
  private final AccountService accounts;
  private final SpatialService service;

  public SpatialController(AccountService a, SpatialService s) {
    accounts = a;
    service = s;
  }

  @GetMapping("/buildings")
  public ResponseEntity<SpatialView> buildings(Principal principal) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.buildings(accounts.current(principal.getName())));
  }
}
