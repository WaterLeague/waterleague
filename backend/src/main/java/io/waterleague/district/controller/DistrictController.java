package io.waterleague.district.controller;

import io.waterleague.district.entity.District;
import io.waterleague.district.repository.DistrictRepository;
import java.util.List;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/districts")
public class DistrictController {
  private final DistrictRepository districts;

  public DistrictController(DistrictRepository d) {
    districts = d;
  }

  @GetMapping
  public List<District> list() {
    return districts.all();
  }
}
