package io.waterleague.account.controller;
import io.waterleague.account.dto.AuthRequest;
import io.waterleague.account.service.AccountService;
import io.waterleague.account.entity.Account;
import io.waterleague.account.mapper.AccountMapper;
import io.waterleague.account.view.AccountView;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import java.security.Principal;
import java.util.*;
@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
 private final AccountService accounts;private final RateLimitService rates;private final JsonService json;
 public AuthController(AccountService a,RateLimitService r,JsonService j){accounts=a;rates=r;json=j;}
 @GetMapping("/csrf") public Map<String,String> csrf(CsrfToken token){return Map.of("token",token.getToken(),"headerName",token.getHeaderName());}
 @PostMapping("/register") public AccountView register(@Valid @RequestBody AuthRequest dto,HttpServletRequest req,HttpServletResponse res){
  rates.check("register:"+json.hash(req.getRemoteAddr()),8,3600);var a=accounts.register(dto);signIn(a,req,res);return AccountMapper.view(a);}
 @PostMapping("/login") public AccountView login(@Valid @RequestBody AuthRequest dto,HttpServletRequest req,HttpServletResponse res){
  rates.check("login-ip:"+json.hash(req.getRemoteAddr()),40,900);rates.check("login-user:"+json.hash(dto.username()),15,900);
  var a=accounts.login(dto);signIn(a,req,res);return AccountMapper.view(a);}
 @GetMapping("/me") public AccountView me(Principal p){return AccountMapper.view(accounts.current(p.getName()));}
 @PostMapping("/logout") public void logout(HttpServletRequest req,HttpServletResponse res){var session=req.getSession(false);if(session!=null)session.invalidate();SecurityContextHolder.clearContext();new HttpSessionCsrfTokenRepository().saveToken(null,req,res);}
 private void signIn(Account a,HttpServletRequest req,HttpServletResponse res){
  req.getSession();req.changeSessionId();
  var context=SecurityContextHolder.createEmptyContext();
  context.setAuthentication(UsernamePasswordAuthenticationToken.authenticated(a.username(),null,List.of(new SimpleGrantedAuthority("ROLE_"+a.role()))));
  SecurityContextHolder.setContext(context);new HttpSessionSecurityContextRepository().saveContext(context,req,res);
  new HttpSessionCsrfTokenRepository().saveToken(null,req,res);
 }
}
