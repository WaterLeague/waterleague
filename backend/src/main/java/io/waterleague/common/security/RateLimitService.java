package io.waterleague.common.security;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import io.waterleague.common.exception.*;
import java.time.Instant;
import java.sql.Timestamp;
@Service
public class RateLimitService {
 private final JdbcTemplate db;private final org.springframework.transaction.support.TransactionTemplate init;
 public RateLimitService(JdbcTemplate db,org.springframework.transaction.PlatformTransactionManager tm){this.db=db;init=new org.springframework.transaction.support.TransactionTemplate(tm);init.setPropagationBehavior(org.springframework.transaction.TransactionDefinition.PROPAGATION_REQUIRES_NEW);}
 @Transactional
 public void check(String key,int max,int seconds){
  var now=Instant.now();
  // 초기 행 생성은 충돌 시 재조회하며 잠금 이후에만 횟수를 증가시킨다.
  try{init.executeWithoutResult(status->db.update("INSERT INTO rate_limits(bucket_key,hits,reset_at) SELECT ?,0,? WHERE NOT EXISTS (SELECT 1 FROM rate_limits WHERE bucket_key=?)",key,Timestamp.from(now.plusSeconds(seconds)),key));}catch(org.springframework.dao.DuplicateKeyException ignored){}
  var row=db.queryForMap("SELECT hits,reset_at FROM rate_limits WHERE bucket_key=? FOR UPDATE",key);
  var reset=db.queryForObject("SELECT reset_at FROM rate_limits WHERE bucket_key=?",(rs,n)->rs.getTimestamp(1).toInstant(),key);
  int hits=((Number)row.get("hits")).intValue();
  if(!reset.isAfter(now)){hits=0;reset=now.plusSeconds(seconds);}
  if(hits>=max)throw new DomainException(ErrorCode.RATE_LIMITED);
  db.update("UPDATE rate_limits SET hits=?,reset_at=? WHERE bucket_key=?",hits+1,Timestamp.from(reset),key);
 }
}
