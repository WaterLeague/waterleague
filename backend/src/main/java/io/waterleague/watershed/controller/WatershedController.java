package io.waterleague.watershed.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.service.WatershedService;
import io.waterleague.watershed.view.WatershedView;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/watersheds")
public class WatershedController {
  private final AccountService accounts;
  private final WatershedService service;
  private final RateLimitService rates;
  private final io.waterleague.watershed.service.WatershedArtifactService artifacts;

  public WatershedController(
      AccountService accounts,
      WatershedService service,
      RateLimitService rates,
      io.waterleague.watershed.service.WatershedArtifactService artifacts) {
    this.accounts = accounts;
    this.service = service;
    this.rates = rates;
    this.artifacts = artifacts;
  }

  @GetMapping("/catalog")
  public ResponseEntity<Map<String, Object>> catalog(Principal p) {
    accounts.current(p.getName());
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.catalog());
  }

  @GetMapping
  public ResponseEntity<List<WatershedView>> list(Principal p) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.list(accounts.current(p.getName()).id()));
  }

  @GetMapping("/{id}")
  public ResponseEntity<WatershedView> get(Principal p, @PathVariable UUID id) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.view(service.require(accounts.current(p.getName()).id(), id)));
  }

  @PostMapping
  public ResponseEntity<WatershedView> create(
      Principal p, @Valid @RequestBody WatershedRequest dto) {
    var owner = accounts.current(p.getName()).id();
    rates.check("watershed:" + owner, 20, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(service.create(owner, dto));
  }

  @GetMapping("/{id}/bundle")
  public void bundle(
      Principal p, @PathVariable UUID id, jakarta.servlet.http.HttpServletResponse response)
      throws java.io.IOException {
    var owner = accounts.current(p.getName()).id();
    rates.check("watershed-bundle:" + owner, 20, 3600);
    var job = service.require(owner, id);
    if (service.view(job).result() != null && service.view(job).result().has("surfaceComparison")) {
      try (var prepared = artifacts.prepareLargeBundle(job)) {
        accounts.current(p.getName());
        response.setContentType("application/zip");
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-watershed-" + id + ".zip");
        response.setContentLengthLong(java.nio.file.Files.size(prepared.path()));
        java.nio.file.Files.copy(prepared.path(), response.getOutputStream());
      }
      return;
    }
    var bytes = artifacts.bundle(job);
    accounts.current(p.getName());
    response.setContentType("application/zip");
    response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
    response.setHeader(
        HttpHeaders.CONTENT_DISPOSITION,
        "attachment; filename=waterleague-watershed-" + id + ".zip");
    response.setContentLength(bytes.length);
    response.getOutputStream().write(bytes);
  }
}
