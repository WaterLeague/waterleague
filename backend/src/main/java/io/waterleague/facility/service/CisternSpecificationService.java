package io.waterleague.facility.service;

import io.waterleague.facility.repository.CisternSpecificationRepository;
import org.springframework.stereotype.Service;

@Service
public class CisternSpecificationService {
  private final CisternSpecificationRepository specifications;

  public CisternSpecificationService(CisternSpecificationRepository specifications) {
    this.specifications = specifications;
  }

  public String catalog() {
    return specifications.raw();
  }

  public String hash() {
    return CisternSpecificationRepository.HASH;
  }
}
