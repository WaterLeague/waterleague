package io.waterleague.analysis.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.analysis.dto.*;
import io.waterleague.analysis.service.ResearchAnalysisService;
import io.waterleague.common.security.RateLimitService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/research")
public class ResearchAnalysisController {
  private final ResearchAnalysisService analysis;
  private final AccountService accounts;
  private final RateLimitService rates;

  public ResearchAnalysisController(
      ResearchAnalysisService a, AccountService s, RateLimitService r) {
    analysis = a;
    accounts = s;
    rates = r;
  }

  private <T> ResponseEntity<T> response(T data) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(data);
  }

  @GetMapping("/comparisons")
  public Object list(Principal p) {
    return response(analysis.list(accounts.current(p.getName())));
  }

  @GetMapping("/comparisons/{id}")
  public Object get(Principal p, @PathVariable UUID id) {
    return response(analysis.get(accounts.current(p.getName()), id));
  }

  @PostMapping("/comparisons")
  public Object create(Principal p, @Valid @RequestBody CreateResearchComparisonRequest dto) {
    var a = accounts.current(p.getName());
    rates.check("research-comparison:" + a.organizationId(), 12, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(analysis.create(a, dto));
  }

  @PostMapping("/patterns")
  public Object patterns(Principal p, @Valid @RequestBody PatternAnalysisRequest dto) {
    var a = accounts.current(p.getName());
    rates.check("research-pattern:" + a.id(), 60, 3600);
    return response(analysis.patterns(a, dto));
  }

  @GetMapping("/comparisons/{id}/jobs/{jobId}/bundle")
  public ResponseEntity<byte[]> bundle(Principal p, @PathVariable UUID id, @PathVariable UUID jobId)
      throws java.io.IOException {
    var a = accounts.current(p.getName());
    rates.check("export:" + a.id(), 20, 3600);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-research-" + id + "-" + jobId + ".zip")
        .contentType(MediaType.parseMediaType("application/zip"))
        .body(analysis.bundle(a, id, jobId));
  }
}
