package io.waterleague.catalog.service;

import io.waterleague.catalog.mapper.CatalogMapper;
import io.waterleague.catalog.repository.CatalogRepository;
import io.waterleague.catalog.view.CatalogView;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
  private final CatalogRepository repository;
  private final CatalogMapper mapper;

  public CatalogService(CatalogRepository repository, CatalogMapper mapper) {
    this.repository = repository;
    this.mapper = mapper;
  }

  public CatalogView overview() {
    return new CatalogView(
        "FOUNDATION", false, repository.findSources().stream().map(mapper::toView).toList());
  }
}
