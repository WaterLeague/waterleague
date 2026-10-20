package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.model.service.LabModelService;
import io.waterleague.simulation.dto.RunRequest;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.simulation.service.SimulationService;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class QueueCapacityTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    String url = System.getProperty("waterleague.integration.jdbc");
    if (url != null) {
      registry.add("spring.datasource.url", () -> url);
      registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
      registry.add("spring.datasource.username", () -> System.getenv("WL_INTEGRATION_USER"));
      registry.add("spring.datasource.password", () -> System.getenv("WL_INTEGRATION_PASSWORD"));
    }
  }

  @Autowired JdbcTemplate db;
  @Autowired SimulationRepository jobs;
  @Autowired SimulationService simulations;
  @Autowired LabModelService model;
  @Autowired io.waterleague.analysis.repository.ResearchAnalysisRepository research;

  @Test
  void sharesGlobalAndOrganizationCapacityWithoutGivingCandidatesPersonalOwnership() {
    UUID org = UUID.randomUUID(), otherOrg = UUID.randomUUID(), owner = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", org, "큐 시험 기관");
    db.update(
        "INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", otherOrg, "다른 큐 시험 기관");
    db.update(
        "INSERT INTO"
            + " accounts(id,username,display_name,password_hash,role,member_type,approval_status,enabled,created_at)"
            + " VALUES(?,?,?,'TEST_ONLY','MEMBER','PLAYER','APPROVED',true,CURRENT_TIMESTAMP)",
        owner,
        "q_" + owner.toString().substring(0, 8),
        "큐 시험");
    UUID strategy = UUID.randomUUID(), version = UUID.randomUUID();
    db.update(
        "INSERT INTO strategies(id,owner_id,title,created_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
        strategy,
        owner,
        "큐 시험");
    db.update(
        "INSERT INTO"
            + " strategy_versions(id,strategy_id,revision,model_hash,input_hash,placements,events,design_note,cost,currency,created_at)"
            + " VALUES(?,?,1,?,?,'[]','[]','큐 상한 시험',0,'KRW',CURRENT_TIMESTAMP)",
        version,
        strategy,
        NativeResearchFixtures.HASH,
        "a".repeat(64));
    List<UUID> candidates = new ArrayList<>();
    for (int i = 0; i < 499; i++) {
      UUID group = UUID.randomUUID(), candidate = UUID.randomUUID();
      db.update(
          "INSERT INTO"
              + " research_searches(id,organization_id,requested_by,request_key,request_hash,model_hash,budget_krw,seed,top_k,candidates_per_arm,provenance,provenance_hash,created_at)"
              + " VALUES(?,?,?,?,?,?,100000000,0,2,1,'{}',?,CURRENT_TIMESTAMP)",
          group,
          i < 7 ? org : otherOrg,
          owner,
          UUID.randomUUID(),
          "b".repeat(64),
          NativeResearchFixtures.HASH,
          "c".repeat(64));
      db.update(
          "INSERT INTO"
              + " research_candidates(id,search_id,arm,ordinal,placements,model_hash,input_hash,cost,state,created_at)"
              + " VALUES(?,?,'PATTERN',1,'[]',?,?,0,'QUEUED',CURRENT_TIMESTAMP)",
          candidate,
          group,
          NativeResearchFixtures.HASH,
          "d".repeat(64));
      candidates.add(candidate);
    }
    assertThat(jobs.totalActive()).isEqualTo(499);
    assertThat(jobs.active(owner)).isZero();
    assertThat(research.active(org)).isEqualTo(7);
    assertThat(jobs.get(candidates.getFirst(), owner)).isEmpty();
    assertThat(jobs.list(owner)).isEmpty();
    var first = simulations.enqueueJob(owner, new RunRequest(version, UUID.randomUUID()));
    assertThat(jobs.totalActive()).isEqualTo(500);
    assertThatThrownBy(
            () -> simulations.enqueueJob(owner, new RunRequest(version, UUID.randomUUID())))
        .isInstanceOf(DomainException.class)
        .hasMessageContaining("요청");
    assertThat(jobs.active(owner)).isEqualTo(1);
    db.update("UPDATE research_candidates SET state='FAILED' WHERE id=?", candidates.getFirst());
    simulations.enqueueJob(owner, new RunRequest(version, UUID.randomUUID()));
    assertThat(jobs.totalActive()).isEqualTo(500);
    assertThat(jobs.active(owner)).isEqualTo(2);
    assertThat(research.active(org)).isEqualTo(6);
    UUID comparison = UUID.randomUUID();
    db.update(
        "INSERT INTO"
            + " rainfall_comparisons(id,owner_id,source_version_id,request_key,request_hash,title,created_at)"
            + " VALUES(?,?,?,?,?,'큐 시험',CURRENT_TIMESTAMP)",
        comparison,
        owner,
        version,
        UUID.randomUUID(),
        "e".repeat(64));
    db.update(
        "INSERT INTO rainfall_comparison_jobs(comparison_id,ordinal,model_hash,job_id)"
            + " VALUES(?,0,?,?)",
        comparison,
        NativeResearchFixtures.HASH,
        first.id());
    db.update(
        "INSERT INTO"
            + " research_comparisons(id,organization_id,requested_by,source_job_id,comparison_id,request_key,request_hash,created_at)"
            + " VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        UUID.randomUUID(),
        org,
        owner,
        first.id(),
        comparison,
        UUID.randomUUID(),
        "f".repeat(64));
    assertThat(research.active(org)).isEqualTo(7);
    db.update("UPDATE simulation_jobs SET state='FAILED' WHERE id=?", first.id());
    assertThat(research.active(org)).isEqualTo(6);
    assertThatThrownBy(
            () ->
                db.update(
                    "UPDATE research_candidates SET model_hash=? WHERE id=?",
                    "0".repeat(64),
                    candidates.get(1)))
        .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
    assertThatThrownBy(
            () ->
                db.update(
                    "UPDATE research_candidates SET state='RUNNING' WHERE id=?", candidates.get(1)))
        .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
  }
}
