package io.waterleague.account.service;
import io.waterleague.account.entity.Account;
import io.waterleague.account.dto.AuthRequest;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import org.springframework.stereotype.Service;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.dao.DuplicateKeyException;
import java.util.UUID;
@Service
public class AccountService {
 private final AccountRepository accounts;private final PasswordEncoder encoder;private final String dummy;
 public AccountService(AccountRepository a,PasswordEncoder e){accounts=a;encoder=e;dummy=e.encode(UUID.randomUUID().toString());}
 public Account register(AuthRequest dto){
  var account=new Account(UUID.randomUUID(),dto.username(),dto.username(),encoder.encode(dto.password()),"PLAYER",null,true);
  try{accounts.add(account);}catch(DuplicateKeyException e){throw new DomainException(ErrorCode.ACCOUNT_UNAVAILABLE);}return account;
 }
 public Account login(AuthRequest dto){var a=accounts.byUsername(dto.username());
  boolean match=encoder.matches(dto.password(),a.map(Account::passwordHash).orElse(dummy));
  if(!match||a.isEmpty()||!a.get().enabled())throw new DomainException(ErrorCode.CREDENTIALS_INVALID);return a.get();}
 public Account current(String username){return accounts.byUsername(username).filter(Account::enabled).orElseThrow(()->new DomainException(ErrorCode.AUTHENTICATION_REQUIRED));}
}
