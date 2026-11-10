import React from 'react';
import {AbsoluteFill, Composition, Easing, Img, interpolate, registerRoot, spring, staticFile, useCurrentFrame} from 'remotion';
import './style.css';

const ease = Easing.bezier(.22, 1, .36, 1);
const ramp = (f: number, a: number, b: number) => interpolate(f, [a,b], [0,1], {extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:ease});
const pop = (f: number, delay = 0) => spring({frame:f-delay,fps:30,config:{damping:19,stiffness:110,mass:.85}});

function Schedule() {
  return <><div className="card-top"><span className="icon">▦</span><span>Расписание</span><span className="tiny">СЕГОДНЯ</span></div><div className="date">Понедельник <span>09</span></div><div className="week">{['ПН','ВТ','СР','ЧТ','ПТ'].map((x,i)=><div key={x} className={i===0?'selected':''}>{x}<b>{9+i}</b></div>)}</div><div className="lesson"><small>09:00 — 10:20</small><strong>Математика</strong><span>Лекция · Ауд. 402</span></div><div className="lesson second"><small>10:35 — 11:55</small><strong>Дизайн интерфейсов</strong><span>Практика · Ауд. 215</span></div></>;
}
function Tasks() {
  const f = useCurrentFrame();
  return <><div className="card-top"><span className="icon">✓</span><span>Задачи</span><span className="count">3</span></div><div className="task-title">Всё по плану.</div><div className="progress"><div style={{width:`${ramp(f,57,85)*68}%`}}/></div><div className="progress-caption">Твой прогресс <b>2 / 3</b></div>{['Конспект по математике','Сдать лабораторную','Подготовиться к зачёту'].map((s,i)=><div className="task" key={s}><span className={i<2?'check done':'check'}>{i<2?'✓':''}</span><span style={{color:i<2?'#8092ae':'#ecf3ff',textDecoration:i<2?'line-through':'none'}}>{s}</span></div>)}<div className="pill">↗ &nbsp; На шаг ближе к цели</div></>;
}
function AI() {
 const f=useCurrentFrame();
 return <><div className="card-top"><span className="icon sparkle">✦</span><span>AI</span><span className="tiny">РЯДОМ</span></div><div className="ai-orb"><div>✦</div></div><div className="ai-question">Когда готовиться к зачёту?</div><div className="ai-answer" style={{opacity:ramp(f,66,77),transform:`translateY(${(1-ramp(f,66,82))*12}px)`}}>Завтра есть свободное окно.<br/><b>Начнём в 14:00?</b></div><div className="ai-bottom"><span/> Учитывает твой ритм</div></>;
}
const Promo = () => {
 const f=useCurrentFrame();
 const intro=pop(f,3), dock=ramp(f,36,53), out=ramp(f,101,113), end=pop(f,108);
 const logoSize=164-112*dock;
 return <AbsoluteFill className="scene">
  <div className="ambient" style={{transform:`translate(${Math.sin(f/60)*35}px,${Math.cos(f/60)*18}px) scale(${1+f/1500})`}}/>
  <div className="grid"/>
  <div className="orbit" style={{opacity:.12+.12*ramp(f,4,34),transform:`translate(-50%,-50%) rotateX(68deg) rotateZ(${-15+f*.06}deg)`}}/>
  <div className="topline"><span className="live-dot"/> UKLADEN <span className="top-right">ТВОЁ ВРЕМЯ. ТВОЙ РИТМ.</span></div>
  <div style={{position:'absolute',left:'50%',top:255-150*dock,display:'flex',alignItems:'center',flexDirection:dock>.7?'row':'column',gap:16,opacity:Math.min(intro,1)*(1-out),transform:`translateX(-50%) scale(${.65+.35*intro})`,filter:`blur(${(1-Math.min(intro,1))*12}px)`}}>
   <div className="logo-tile" style={{width:logoSize,height:logoSize,borderRadius:logoSize*.23}}><Img src={staticFile('logo.png')} style={{width:'100%',height:'100%'}}/></div>
   <div style={{fontSize:42-14*dock,fontWeight:600,letterSpacing:-1.7,opacity:ramp(f,14,28)}}>Ukladen<span style={{color:'#6caaff'}}>.</span></div>
  </div>
  <div className="intro-line" style={{opacity:ramp(f,20,32)*(1-ramp(f,34,44)),transform:`translateY(${(1-ramp(f,20,32))*10}px)`}}>Меньше хаоса. Больше возможностей.</div>
  <div style={{position:'absolute',inset:0,perspective:1400,opacity:1-out,transform:`scale(${1-out*.13}) translateY(${-out*35}px)`,filter:`blur(${out*10}px)`}}>
   {[Schedule,Tasks,AI].map((Content,i)=>{
    const p=pop(f,44+i*5), x=[-343,0,343][i], rotation=[-9,0,9][i];
    return <div key={i} className={`card card-${i}`} style={{left:640+x-158,top:226+(i===1?-15:12),zIndex:i===1?3:2,opacity:Math.min(1,Math.max(0,p)),transform:`translate3d(${(1-p)*(i===0?-200:i===2?200:0)}px,${(1-p)*230+Math.sin((f+i*13)/35)*3}px,${i===1?45:0}px) rotateX(${(1-p)*24+3}deg) rotateY(${rotation*p}deg) rotateZ(${(1-p)*(i-1)*15}deg) scale(${.8+.2*p})`}}><Content/></div>;
   })}
  </div>
  <div className="closing" style={{opacity:Math.min(1,end),transform:`translateY(${(1-end)*38}px) scale(${.96+.04*end})`,filter:`blur(${(1-Math.min(end,1))*9}px)`}}>
   <div className="logo-tile final-logo"><Img src={staticFile('logo.png')} style={{width:'100%'}}/></div>
   <div className="final-title">Ukladen <span>—</span></div>
   <div className="final-subtitle">учёба под контролем</div>
   <div className="final-rule" style={{transform:`scaleX(${ramp(f,121,140)})`}}/>
  </div>
  <div className="footer"><span>ОДНО ПРОСТРАНСТВО ДЛЯ ГЛАВНОГО</span><span className="footer-line"/><span>РАСПИСАНИЕ · ЗАДАЧИ · AI</span></div>
 </AbsoluteFill>;
};
registerRoot(()=> <Composition id="Ukladen" component={Promo} durationInFrames={150} fps={30} width={1280} height={720}/>);
