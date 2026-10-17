package io.waterleague.disaster.service;

import io.waterleague.disaster.repository.DisasterRepository;
import io.waterleague.disaster.view.DisasterView;
import org.springframework.stereotype.Service;

@Service
public class DisasterService {
  private final DisasterRepository events;

  public DisasterService(DisasterRepository events) {
    this.events = events;
  }

  public DisasterView catalog() {
    return events.all();
  }

  public void requireModel(String districtId, String hash) {
    events.require(districtId, hash);
  }
}
