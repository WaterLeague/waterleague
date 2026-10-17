package io.waterleague.installation.controller;

import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.mapper.InstallationMapper;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.installation.view.InstallationView;
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
  public List<InstallationView> list() {
    return service.active().stream().map(InstallationMapper::view).toList();
  }

  @GetMapping("/sites")
  public List<io.waterleague.installation.view.SiteView> sites() {
    return service.sites();
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public InstallationView install(Principal p, @Valid @RequestBody InstallRequest dto) {
    rates.check("shared-install:" + json.hash(p.getName()), 60, 60);
    return InstallationMapper.view(service.install(p.getName(), dto));
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void remove(Principal p, @PathVariable UUID id) {
    rates.check("shared-install:" + json.hash(p.getName()), 60, 60);
    service.remove(p.getName(), id);
  }
}
