package io.waterleague.installation.controller;

import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.installation.view.InstallationView;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/installations")
public class InstallationController {
  private final InstallationService service;
  private final io.waterleague.common.security.RateLimitService rates;
  private final io.waterleague.common.service.JsonService json;

  public InstallationController(
      InstallationService service,
      io.waterleague.common.security.RateLimitService rates,
      io.waterleague.common.service.JsonService json) {
    this.service = service;
    this.rates = rates;
    this.json = json;
  }

  @GetMapping
  public List<InstallationView> list(
      Principal p, @RequestParam(required = false) UUID competitionId) {
    return service.activeViews(p == null ? null : p.getName(), competitionId);
  }

  @GetMapping("/sites")
  public io.waterleague.installation.view.SitePageView sites(
      @RequestParam(required = false) String districtId,
      @RequestParam(defaultValue = "0") double x,
      @RequestParam(defaultValue = "0") double y,
      @RequestParam(defaultValue = "0") int offset,
      @RequestParam(required = false) io.waterleague.strategy.entity.FacilityType type,
      @RequestParam(defaultValue = "false") boolean vacant,
      @RequestParam(required = false) io.waterleague.installation.entity.SiteSurface surface,
      HttpServletRequest request) {
    checkRead(request);
    return service.sites(districtId, x, y, offset, type, vacant, surface);
  }

  @GetMapping("/counts")
  public Map<String, Integer> counts(
      Principal p, @RequestParam(required = false) UUID competitionId) {
    return service.activeCounts(p == null ? null : p.getName(), competitionId);
  }

  @GetMapping("/sites/{districtId}/building")
  public io.waterleague.installation.view.SiteView building(
      @PathVariable String districtId, @RequestParam String sourceId, HttpServletRequest request) {
    checkRead(request);
    return service.building(districtId, sourceId);
  }

  @GetMapping("/sites/ground")
  public io.waterleague.installation.view.SiteView ground(
      @RequestParam double x, @RequestParam double y, HttpServletRequest request) {
    checkRead(request);
    return service.ground(x, y);
  }

  @GetMapping("/sites/{districtId}/{cellId}")
  public io.waterleague.installation.view.SiteView site(
      @PathVariable String districtId, @PathVariable String cellId, HttpServletRequest request) {
    checkRead(request);
    return service.site(districtId, cellId);
  }

  private void checkRead(HttpServletRequest request) {
    rates.check("native-site:" + json.hash(request.getRemoteAddr()), 300, 60);
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public InstallationView install(
      Principal p,
      @Valid @RequestBody InstallRequest dto,
      @RequestParam(required = false) UUID competitionId) {
    rates.check("shared-install:" + json.hash(p.getName()), 60, 60);
    return service.view(service.install(p.getName(), dto, competitionId));
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void remove(Principal p, @PathVariable UUID id) {
    rates.check("shared-install:" + json.hash(p.getName()), 60, 60);
    service.remove(p.getName(), id);
  }
}
