package io.waterleague;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@org.springframework.scheduling.annotation.EnableScheduling
@SpringBootApplication
public class WaterLeagueApplication {

  public static void main(String[] args) {
    SpringApplication.run(WaterLeagueApplication.class, args);
  }
}
