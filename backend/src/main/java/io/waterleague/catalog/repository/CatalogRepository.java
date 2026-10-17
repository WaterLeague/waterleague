package io.waterleague.catalog.repository;

import io.waterleague.catalog.entity.Dataset;
import java.util.List;

public interface CatalogRepository {
  List<Dataset> findSources();
}
