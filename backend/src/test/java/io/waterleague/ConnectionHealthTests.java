package io.waterleague;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import io.waterleague.common.controller.ConnectionHealthController;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ConnectionHealthTests {
  @Test
  void returnsOnlyUncachedReachabilityWithoutSessionOrInternalDetails() throws Exception {
    var client = MockMvcBuilders.standaloneSetup(new ConnectionHealthController()).build();
    client.perform(get("/api/v1/health"))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(header().doesNotExist("Set-Cookie"))
        .andExpect(content().json("{\"status\":\"UP\"}"))
        .andExpect(jsonPath("$.length()").value(1));
    client.perform(post("/api/v1/health")).andExpect(status().isMethodNotAllowed());
  }
}
