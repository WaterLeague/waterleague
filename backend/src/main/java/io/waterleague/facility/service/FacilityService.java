package io.waterleague.facility.service;

import io.waterleague.facility.repository.FacilityRepository;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class FacilityService {
  private final FacilityRepository repository;

  public FacilityService(FacilityRepository repository) {
    this.repository = repository;
  }

  public String digest(boolean previous) {
    return previous ? FacilityRepository.LEGACY_SHA256 : FacilityRepository.SHA256;
  }

  public JsonNode catalog(boolean previous) {
    return repository.catalog(previous);
  }
}
