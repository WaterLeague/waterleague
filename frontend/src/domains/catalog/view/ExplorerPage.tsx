import { lazy, Suspense, useState, useEffect, useRef } from 'react';
import { ArrowUpRight, ArrowRight, Layers3, MapPin, Scan, RotateCcw, Box, PanelRightClose, PanelRightOpen, ShieldCheck, Database, FlaskConical, Check, ChevronDown, CircleHelp, MousePointer2, Move, LockKeyhole, X, FileCheck2, Download, Compass, Building2, AlertCircle } from 'lucide-react';
import { useCatalog } from '../controller/useCatalog';
import { buildingLabel, heightDescription } from '../service/catalogService';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
const MapScene=lazy(() => import('./MapScene'));
const nf=new Intl.NumberFormat('ko-KR');
const sources=[{name:'건물 경계',provider:'OpenStreetMap',state:'확보',ok:true},{name:'관측 강우',provider:'NOAA · 서울 관측소',state:'품질 검토',ok:false},{name:'지표고 · 토지피복',provider:'공식 원자료 필요',state:'미확보',ok:false},{name:'배수 · 현장 관측',provider:'수문 검증 필요',state:'미확보',ok:false}];

export function ExplorerPage() {
  const {data,error,retry}=useCatalog();
  const [selected,setSelected]=useState<string|null>(null);
  const [topView,setTopView]=useState(false),[reset,setReset]=useState(0),[panel,setPanel]=useState(true);
  const [tab,setTab]=useState<'map'|'quality'|'research'>('map');
  const [help,setHelp]=useState(false),[list,setList]=useState(false);
  const dialogRef=useRef<HTMLElement>(null);
  useEffect(()=>{
    if(!help)return;
    const previous=document.activeElement as HTMLElement|null;
    const dialog=dialogRef.current;
    dialog?.querySelector<HTMLButtonElement>('button')?.focus();
    function handleKey(event:KeyboardEvent){
      if(event.key==='Escape'){setHelp(false);return;}
      if(event.key!=='Tab'||!dialog)return;
      const items=Array.from(dialog.querySelectorAll<HTMLElement>('button,a[href],[tabindex="0"]'));
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
    document.addEventListener('keydown',handleKey);
    return()=>{document.removeEventListener('keydown',handleKey);previous?.focus();};
  },[help]);
  const building=data?.map.buildings.find(b=>b.id===selected);
  return <div className="app-shell">
    <header className="topbar"><a className="wordmark" href="/" aria-label="WATER LEAGUE 홈"><svg width="31" height="31" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M3 10c5-6 10 6 15 0s8 0 11 0M3 17c5-6 10 6 15 0s8 0 11 0M3 24c5-6 10 6 15 0s8 0 11 0" stroke="currentColor" strokeWidth="3.4"/></svg><span>WATER LEAGUE<small>시민의 설계, 도시의 변화</small></span></a>
      <nav aria-label="주요 화면"><button aria-current={tab==='map'?'page':undefined} className={tab==='map'?'active':''} onClick={()=>setTab('map')}>지역 탐색</button><button aria-current={tab==='quality'?'page':undefined} className={tab==='quality'?'active':''} onClick={()=>setTab('quality')}>데이터 검증</button><button aria-current={tab==='research'?'page':undefined} className={tab==='research'?'active':''} onClick={()=>setTab('research')}>연구 원칙</button></nav>
      <div className="topbar-end"><span className="phase"><i/>개발 프리뷰</span><button className="icon-button" aria-label="사용 안내" onClick={()=>setHelp(true)}><CircleHelp size={19}/></button></div></header>
    <div className="workspace">
      <aside className="project-panel"><div className="eyebrow">REGION EXPLORER <span>01</span></div><h1>서울 성수동<span>빗물의 길을 읽는 첫 단계</span></h1>
        <div className="location"><MapPin size={14}/> 성동구 · 연무장길 일대</div>
        <div className="region-sketch" aria-hidden="true"><svg viewBox="-155 -160 310 320">{data?.map.buildings.map(b=><polygon key={b.id} points={b.coordinates.map(([x,y])=>`${x},${-y}`).join(' ')}/>)}</svg><span>실제 건물 경계 평면<br/>37.54425° N · 127.05400° E</span></div>
        <div className="region-stats"><div><strong>{data?data.map.buildings.length:'—'}</strong><span>공개 건물 경계</span></div><div><strong>01<small> / 후보</small></strong><span>수문 검증 전</span></div></div>
        <div className="section-label">자료 준비 현황 <span>01 / 04</span></div><div className="source-list">{sources.map(source=><div className="source-row" key={source.name}><div className={source.ok?'source-icon done':'source-icon'}>{source.ok?<Check size={13}/>:<span/>}</div><div><b>{source.name}</b><small>{source.provider}</small></div><span className={source.ok?'state done':'state'}>{source.state}</span></div>)}</div>
        <button className="text-button" onClick={()=>setTab('quality')}>출처와 검증 내역 <ArrowRight size={15}/></button>
        <div className="project-note"><ShieldCheck size={19}/><p>현실에 적용할 수 있는 결과는<br/><b>검증된 데이터에서 시작합니다.</b></p></div>
        <a className="source-credit" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors <ArrowUpRight size={12}/></a>
      </aside>
      <main className="main-workspace">
        <div className="workspace-bar"><div><span className="crumb">서울 / 성동구</span><ChevronDown size={13}/><span className="draft-pill">탐색용 데이터</span></div><span className="workspace-subtitle">공개 원본 기반 · 수문모델 미승인</span></div>
        {tab==='map'?<div className="map-layout"><section className="map-stage" aria-label="성수동 공개 건물 3D 탐색">
          <div className="map-topline"><span><i/> 실제 건물 경계</span><span>표고 평탄화 · 높이 일부 가정</span></div>
          {error?<div className="loading-state"><AlertCircle/><p>{error}</p><button onClick={retry}>다시 불러오기</button></div>:!data?<div className="loading-state"><Layers3/><p>공개 지형 자료를 불러오는 중</p></div>:<ErrorBoundary fallback={<div className="loading-state"><p>이 환경에서 3D를 표시할 수 없습니다.</p><button onClick={()=>setList(true)}>건물 목록으로 탐색</button></div>}><Suspense fallback={<div className="loading-state">3D 장면 준비 중</div>}><MapScene map={data.map} selected={selected} onSelect={setSelected} topView={topView} reset={reset}/></Suspense></ErrorBoundary>}
          <div className="map-compass"><Compass size={36} strokeWidth={1}/><span>N</span></div>
          <div className="map-controls"><button aria-label={topView?'입체 보기':'위에서 보기'} aria-pressed={topView} onClick={()=>setTopView(v=>!v)}>{topView?<Box size={19}/>:<Scan size={19}/>}</button><button aria-label="시점 초기화" onClick={()=>setReset(v=>v+1)}><RotateCcw size={18}/></button><span/><button aria-label="건물 목록" aria-pressed={list} onClick={()=>setList(v=>!v)}><Building2 size={19}/></button><button aria-label={panel?'상세 패널 닫기':'상세 패널 열기'} onClick={()=>setPanel(v=>!v)}>{panel?<PanelRightClose size={19}/>:<PanelRightOpen size={19}/>}</button></div>
          {list&&<div className="building-list"><div><b>건물 목록</b><button className="icon-button" aria-label="건물 목록 닫기" onClick={()=>setList(false)}><X size={16}/></button></div><p>목록에서도 건물을 선택할 수 있습니다.</p>{data?.map.buildings.map(b=><button key={b.id} className={selected===b.id?'selected':''} onClick={()=>{setSelected(b.id);setPanel(true);}}>{buildingLabel(b)}<ArrowRight size={13}/></button>)}</div>}
          <div className="map-bottom"><span><MousePointer2 size={13}/> 건물 선택</span><span><Move size={13}/> 드래그 회전 · 스크롤 확대</span><button onClick={()=>setHelp(true)}>조작 안내</button></div>
          <div className="map-title"><span>SEONGSU, SEOUL</span><p>도시를 이해하는 것부터.</p></div>
        </section>{panel&&<aside className="detail-panel"><div className="detail-heading"><span className="eyebrow">{building?'SELECTED BUILDING':'SITE OVERVIEW'}</span><Layers3 size={17}/></div>
          <h2>{building?buildingLabel(building):'설계 전에, 지역 읽기'}</h2><p className="panel-intro">{building?'공개 원본의 형상과 표현에 사용한 정보를 확인하세요.':'건물을 선택해 공개 공간정보를 살펴보세요. 설치 후보지는 배수·현장 검증 후 열립니다.'}</p>
          {building?<><div className="building-symbol"><Building2 size={48} strokeWidth={1}/><span>{building.id}</span></div><dl className="properties"><div><dt>화면상 추정 면적</dt><dd>{nf.format(building.displayAreaM2)} <small>m²</small></dd></div><div><dt>표현 높이</dt><dd>{building.heightM} <small>m</small></dd></div><div><dt>높이 근거</dt><dd>{heightDescription(building)}</dd></div><div><dt>현장 설치 가능성</dt><dd className="amber-text">미확인</dd></div></dl><p className="micro-note">화면 면적·높이는 공식 설치 제원으로 사용할 수 없습니다.</p><a className="outline-button" href={`https://www.openstreetmap.org/${building.id}`} target="_blank" rel="noreferrer">공개 원본 확인 <ArrowUpRight size={14}/></a></>:<><div className="water-diagram" aria-hidden="true"><svg viewBox="0 0 240 120"><path d="M16 85 92 43 224 72 146 115Z" fill="#dce7d3"/><path d="M60 62 60 29 100 9 100 43Z" fill="#9aaea0"/><path d="M100 9 158 23 158 59 100 43Z" fill="#c5d2c4"/><path d="M60 29 100 9 158 23 118 43Z" fill="#e6ecdf"/><path d="M24 81 99 49 211 75" stroke="#527c63" strokeDasharray="4 4" fill="none"/><path d="m164 36-6 9m17-6-6 9m17-6-6 9" stroke="#7da4ac" strokeWidth="2"/></svg><span>관측 → 모델 → 설계 → 검증</span></div><div className="step-item"><span>01</span><div><b>실제 공간을 확인하고</b><p>건물 경계와 자료의 출처 확인</p></div></div><div className="step-item"><span>02</span><div><b>물의 경로를 검증한 뒤</b><p>강우·지형·배수·토양 연결</p></div></div><div className="step-item muted"><span>03</span><div><b>같은 조건에서 설계 경쟁</b><p>서버 계산과 재현 가능한 기록</p></div></div></>}
          <div className="evaluation-gate"><div><LockKeyhole size={16}/><b>공식 평가 준비 중</b></div><p>검증된 수문모델이 등록되기 전에는 시설 효과나 랭킹을 생성하지 않습니다.</p><button onClick={()=>setTab('quality')}>남은 검증 확인 <ArrowRight size={14}/></button></div>
        </aside>}</div>:<section className="document-page">{tab==='quality'?<><span className="eyebrow">DATA & EVIDENCE</span><h2>출처부터, 검증까지.</h2><p className="document-lead">공개된 자료가 있다는 것과 연구에 사용할 준비가 되었다는 것은 다릅니다.</p><div className="audit-grid"><article><Database size={23}/><span className="state done">시각화 가능</span><h3>성수동 건물 경계</h3><strong>{data?.map.buildings.length??'—'}<small>개 형상</small></strong><p>OpenStreetMap 원본에서 추출한 실제 건물 경계입니다. 미확보 높이와 지표고에는 시각화 가정이 포함됩니다.</p><a href="/data/seongsu.json" download>파생 자료 내려받기 <Download size={14}/></a></article><article><FlaskConical size={23}/><span className="state">계산 사용 보류</span><h3>서울 관측소 · 2024</h3><strong>{data?nf.format(data.rainfall.rowCount):'—'}<small>개 관측 레코드</small></strong><p>NOAA 공개자료에 누적기간 혼합과 결측이 있어 강우 입력으로 승인하지 않았습니다. 사용 가능한 이벤트는 0개입니다.</p><a href="/data/rainfall-audit.json" download>품질 점검 기록 <Download size={14}/></a></article></div><h3 className="subheading">공식 계산을 열기 위한 조건</h3><div className="checklist">{['관측 강우의 시간해상도·결측·품질코드 검증','DEM·토지피복·실제 배수경계와 출구 확보','시설 단면·유입 연결·설치 제약 검토','SWMM 기준안·물수지·참조 사례 대조','모델 목적·검증 범위 검토 및 승인'].map((s,i)=><div key={s}><span>{String(i+1).padStart(2,'0')}</span><p>{s}</p><b>대기</b></div>)}</div><p className="footnote">자료 수집 및 확인: 2026.10.15 · <a href="https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database" target="_blank" rel="noreferrer">NOAA ISD 안내</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OSM 이용조건</a></p></>:<><span className="eyebrow">RESEARCH BY DESIGN</span><h2>좋은 점수보다,<br/>설명할 수 있는 결과.</h2><p className="document-lead">시민의 설계가 연구의 출발점이 되도록, 결과에 이르는 과정까지 남깁니다.</p><div className="principle-list">{[{icon:<Database/>,title:'입력의 출처를 보존',body:'실측·공개 공간자료·파생값·보정값·가정값을 구분합니다. 모델과 강우 원본은 버전·해시로 고정합니다.'},{icon:<FileCheck2/>,title:'검증한 범위 안에서 해석',body:'탐색, 참조 검증, 현장 검증을 구분합니다. 현장 관측으로 검증하지 않은 결과를 실제 효과로 표현하지 않습니다.'},{icon:<ShieldCheck/>,title:'같은 조건, 다시 가능한 실험',body:'시설 배치·변경 이력·엔진·초기상태·시계열을 묶어 재현합니다. 공식 점수는 서버 검증을 통과한 결과만 사용합니다.'}].map(item=><article key={item.title}>{item.icon}<div><h3>{item.title}</h3><p>{item.body}</p></div></article>)}</div><div className="research-note"><LockKeyhole size={20}/><p>기관은 소속과 이용 목적이 확인된 범위에서, 플레이어가 동의한 전략만 열람할 수 있도록 설계합니다.</p></div></>}</section>}
        <footer className="statusbar"><span><i/> 공개자료 탐색 워크스페이스</span><span>MODEL STATUS <b>DRAFT</b></span><span>기준 데이터 2026.10.15</span></footer>
      </main>
    </div>
    {help&&<div className="modal-backdrop" onClick={()=>setHelp(false)}><section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="help-title" className="help-dialog" onClick={e=>e.stopPropagation()}><button className="icon-button close" aria-label="안내 닫기" onClick={()=>setHelp(false)}><X/></button><span className="eyebrow">QUICK GUIDE</span><h2 id="help-title">지역을 천천히 살펴보세요.</h2><p>드래그로 회전, 스크롤로 확대할 수 있습니다. 건물을 클릭하면 원본과 높이 가정을 확인합니다.</p><p>키보드는 ‘건물 목록’ 버튼과 목록 항목을 이용하세요. ‘위에서 보기’와 ‘시점 초기화’로 시점을 바꿀 수 있습니다.</p><div className="research-note">현재는 실제 데이터 탐색 프리뷰입니다. 시설 배치·SWMM·공식 랭킹은 아직 제공하지 않습니다.</div><button className="primary-button" onClick={()=>setHelp(false)}>탐색 시작 <ArrowRight size={16}/></button></section></div>}
  </div>;
}
