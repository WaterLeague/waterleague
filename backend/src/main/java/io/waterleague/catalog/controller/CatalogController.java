package io.waterleague.catalog.controller;
import io.waterleague.catalog.service.CatalogService;
import io.waterleague.catalog.view.CatalogView;
import org.springframework.web.bind.annotation.*;
import java.util.List;
@RestController
@RequestMapping("/api/v1")
public class CatalogController {
    private final CatalogService service;
    public CatalogController(CatalogService service) { this.service = service; }
    @GetMapping("/catalog") public CatalogView overview() { return service.overview(); }
    @GetMapping("/maps") public List<Object> maps() { return List.of(); }
}
