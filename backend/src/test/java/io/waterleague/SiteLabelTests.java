package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.installation.repository.SiteLabelRepository;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class SiteLabelTests {
  @Test
  void servesSourceBuildingNameAddressAndStableNumber() {
    var labels = new SiteLabelRepository(new JsonService(new ObjectMapper()));
    var value = labels.require("C00000ce622e09957b3ff9d76");
    assertThat(value.name()).isEqualTo("경성자동차공업사 옥상 · 1");
    assertThat(value.address()).isEqualTo("서울특별시 금천구 가산로 86");
    assertThat(labels.require("C0000223a07c9e88de4abf854").name()).isEqualTo("지오빌 옥상 · 1");
    assertThat(labels.require("C00000ce622e09957b3ff9d76")).isEqualTo(value);
    assertThatThrownBy(() -> labels.require("../../missing")).isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> labels.require("Cffffffffffffffffffffffff")).isInstanceOf(DomainException.class);
  }
}
