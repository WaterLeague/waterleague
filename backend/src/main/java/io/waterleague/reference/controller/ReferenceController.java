package io.waterleague.reference.controller;

import io.waterleague.reference.service.ReferenceService;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/references")
public class ReferenceController {
  private final ReferenceService references;

  public ReferenceController(ReferenceService r) {
    references = r;
  }

  @GetMapping
  public Object list() {
    return references.view();
  }

  @GetMapping("/source")
  public ResponseEntity<String> source() {
    return download("cpu-reference.json", references.source());
  }

  @GetMapping("/ledger")
  public ResponseEntity<String> ledger() {
    return download("cpu-search-ledger.json", references.ledger());
  }

  private ResponseEntity<String> download(String name, String content) {
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + name + "\"")
        .body(content);
  }
}
