package io.waterleague.infrastructure.service;

import io.waterleague.infrastructure.mapper.InfrastructureMapper;
import io.waterleague.infrastructure.repository.InfrastructureRepository;
import io.waterleague.infrastructure.view.InfrastructureView;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class InfrastructureService {
  private final InfrastructureRepository repository;
  private final InfrastructureMapper mapper;

  public InfrastructureService(InfrastructureRepository repository, InfrastructureMapper mapper) {
    this.repository = repository;
    this.mapper = mapper;
  }

  public InfrastructureView referenceCatalog() {
    // 삭제 여부와 자료 기준일은 실제 철거·준공·운전 시점의 증거가 아니다.
    return new InfrastructureView(
        InfrastructureRepository.VERSION, InfrastructureRepository.SHA256, "REFERENCE_ONLY",
        repository.sources(), repository.records().stream().collect(Collectors.groupingBy(
            a -> a.displayStatus(), Collectors.counting())),
        repository.records().stream().filter(a -> a.displayStatus().equals("REFERENCE"))
            .map(mapper::toView).toList());
  }
}
