"""Football score predictor - paid access (access codes). Phone-friendly Streamlit app.
Needs predictor_nokey.py beside it.

Secrets to set in Streamlit (Manage app > Settings > Secrets):
  CODE_SECRET      = "long random text, keep private"
  ADMIN_PASSWORD   = "your owner password"
  PRICE_TEXT       = "UGX 2,000 per day"
  PAY_INSTRUCTIONS = "Send to MTN MoMo 07XXXXXXXX (Your Name)"
  WHATSAPP_NUMBER  = "2567XXXXXXXX"      (international format, no +)
  FOOTBALL_DATA_ORG_KEY = "your football-data.org key"   (same-day results + key players)

Optional file beside this one: injuries.txt  (one line per team, see the file itself)
"""
import contextlib
import hashlib
import hmac
import html
import io
import json
import math
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import picks as pk
import predictor_nokey as p

st.set_page_config(page_title="Score Predictor", page_icon="⚽")

st.markdown("""
<style>
.big-score {text-align:center; font-size:3.2rem; font-weight:800; line-height:1.1; margin:0.2rem 0;}
.teams {text-align:center; font-size:1.1rem; opacity:0.85;}
.sub {text-align:center; opacity:0.7; margin-bottom:0.8rem;}
.form {font-size:1.3rem; letter-spacing:2px;}
.pick {border:1px solid rgba(128,128,128,.35); border-radius:14px; padding:10px 14px; margin:0 0 10px 0;}
.pick .meta {opacity:.65; font-size:.82rem;}
.pick .vs {font-weight:700; font-size:1.05rem; margin:2px 0 8px 0;}
.pill {display:inline-block; border-radius:999px; padding:4px 11px; margin:0 6px 6px 0; font-size:.88rem; font-weight:600; background:#dce9ff; color:#164a9a;}
.pill.hot {background:#d6f5df; color:#14532d;}
.pill.lock {background:#e5e7eb; color:#555;}
.pill.miss {background:#fde2e2; color:#7f1d1d;}
.day {margin:18px 0 6px 0; font-weight:700; opacity:.65; text-transform:uppercase; font-size:.8rem; letter-spacing:.06em;}
/* virtual match runs full screen behind the page */
iframe[srcdoc] {position:fixed !important; top:0; left:0; width:100vw !important; height:100vh !important;
  height:100dvh !important; border:0; z-index:0; pointer-events:none;}
div:has(> iframe[srcdoc]) {height:0 !important; min-height:0 !important; margin:0 !important; padding:0 !important;}
body {background:#050a1c;}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {background:transparent !important;}
.hero {position:relative; z-index:1; min-height:32vh; display:flex; flex-direction:column; justify-content:flex-end;
  padding-bottom:.7rem; color:#fff; text-shadow:0 2px 14px rgba(0,0,0,.9);}
.hero-t {font-size:2.1rem; font-weight:800; line-height:1.1;}
.hero-s {opacity:.85; font-size:.9rem;}
:root {--sheet-bg: rgba(255,255,255,.97);}
.st-key-sheet {position:relative; z-index:1; background:var(--sheet-bg); border-radius:22px 22px 0 0;
  padding:1rem 1rem 2rem 1rem; box-shadow:0 -6px 24px rgba(0,0,0,.4);}
/* solid toolbar so page content never shows through behind the Share / star / menu icons */
[data-testid="stHeader"] {background:var(--sheet-bg) !important; backdrop-filter:blur(6px);}
</style>
""", unsafe_allow_html=True)

PASSES = {"Daily (24 hours)": 24, "Weekly (7 days)": 24 * 7, "Monthly (30 days)": 24 * 30}

# ---------- virtual live match (simulation, shown beside the title) ----------
VIRTUAL_HTML_2D = """
<style>
 html,body{margin:0;background:#050a1c;overflow:hidden}
 #w{position:fixed;top:0;left:0;width:100%;overflow:hidden;background:#050a1c}
 canvas{width:100%;aspect-ratio:16/9;display:block}
</style>
<div id="w"><canvas id="c"></canvas></div>
<script>
const TEAMS=[
 {c:"ARS",kit:"#e11d2e",sh:"#ffffff",so:"#e11d2e"},{c:"CHE",kit:"#1d4ed8",sh:"#1d4ed8",so:"#ffffff"},
 {c:"MCI",kit:"#7dd3fc",sh:"#ffffff",so:"#7dd3fc"},{c:"LIV",kit:"#c8102e",sh:"#c8102e",so:"#c8102e"},
 {c:"BAR",kit:"#7c3aed",sh:"#1e3a8a",so:"#1e3a8a"},{c:"RMA",kit:"#f8fafc",sh:"#f8fafc",so:"#f8fafc"},
 {c:"INT",kit:"#0f4c9c",sh:"#111827",so:"#0f4c9c"},{c:"BAY",kit:"#dc2626",sh:"#ffffff",so:"#dc2626"}];
const c=document.getElementById('c'),g=c.getContext('2d');
let W=0,H=0,stands=null,cam=.5,fr=0,cf=[];
const DPR=2,SP=.0042;
const SK=['#f1c27d','#e0ac69','#c68642','#8d5524','#5c3a21'],HR=['#161616','#3b2314','#d4a017','#0d0d0d'];
const F0=[[.04,.5],[.2,.3],[.2,.7],[.38,.5],[.55,.32],[.55,.68]],NUM=[1,4,5,8,9,10];
let A,B,score,min,ft,ftWait,pl,ref,ball,poss,st,hold,carryT,fl,celT,cmT,cmTxt,scorer,rot=0,flashT=0;

function fit(){
  W=c.width=Math.round(c.clientWidth*DPR);H=c.height=Math.round(c.clientHeight*DPR);buildStands();
  
}
function buildStands(){
  stands=document.createElement('canvas');stands.width=W*2;stands.height=Math.round(H*.31);
  const q=stands.getContext('2d');q.fillStyle='#10162e';q.fillRect(0,0,stands.width,stands.height);
  const cols=['#e5484d','#3b82f6','#f1f5f9','#fbbf24','#94a3b8','#22c55e','#1e293b'];
  for(let i=0;i<3200;i++){
    q.fillStyle=cols[Math.floor(Math.random()*cols.length)];q.globalAlpha=.5+Math.random()*.5;
    q.beginPath();q.arc(Math.random()*stands.width,Math.random()*stands.height,H*.005+Math.random()*H*.005,0,7);q.fill();
  }
  q.globalAlpha=1;const gr=q.createLinearGradient(0,0,0,stands.height);
  gr.addColorStop(0,'rgba(5,8,20,.8)');gr.addColorStop(1,'rgba(5,8,20,0)');q.fillStyle=gr;q.fillRect(0,0,stands.width,stands.height);
}
const PH=()=>H*.17,TOP=()=>H*.43,BOT=()=>H*.93;
function P(x,y,z){
  z=z||0;const s=.56+.44*y,gy=TOP()+(BOT()-TOP())*y;
  return {x:W/2+(x-cam)*W*1.75*s,y:gy-z*PH()*s,s:s};
}
function rr(x,y,w,h,r){g.beginPath();g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath()}
function ln(a,b){g.beginPath();g.moveTo(a.x,a.y);g.lineTo(b.x,b.y);g.stroke()}
function line2(x1,y1,x2,y2,w,col){g.strokeStyle=col;g.lineWidth=w;g.beginPath();g.moveTo(x1,y1);g.lineTo(x2,y2);g.stroke()}
function lum(h){const n=parseInt(h.slice(1),16);return (((n>>16)&255)*.3+((n>>8)&255)*.59+(n&255)*.11)/255}

// ---------- simulation ----------
function mk(t){return F0.map((f,i)=>({t:t,gk:i==0,x:t?1-f[0]:f[0],y:f[1],hx:t?1-f[0]:f[0],hy:f[1],f:t?-1:1,
  ph:Math.random()*6,sp:0,num:NUM[i],sk:SK[Math.floor(Math.random()*5)],hr:HR[Math.floor(Math.random()*4)],cel:false}))}
function start(){
  let i=Math.floor(Math.random()*8),j;do{j=Math.floor(Math.random()*8)}while(j==i);
  A=TEAMS[i];B=TEAMS[j];score=[0,0];min=0;ft=false;ftWait=0;cf=[];
  pl=[mk(0),mk(1)];
  ref={x:.5,y:.8,f:1,ph:0,sp:0,sk:SK[1],hr:HR[0],num:'',cel:false};
  kickoff(0);cm('Kick off!');cam=.5;
}
function cm(t){cmTxt=t;cmT=75}
function kickoff(t){
  pl.forEach(tm=>tm.forEach(p=>{p.x=p.hx;p.y=p.hy;p.cel=false;p.sp=0}));
  poss=t;hold={t:t,i:3};const p=pl[t][3];p.x=.5+(t?.012:-.012);p.y=.5;
  ball={x:.5,y:.5,z:0};st='carry';carryT=30;fl=null;
}
function moveTo(p,tx,ty,sp){
  const dx=tx-p.x,dy=ty-p.y,d=Math.hypot(dx,dy);let vx=0,vy=0;
  if(d>.003){const m=Math.min(sp,d);vx=dx/d*m;vy=dy/d*m}
  p.x=Math.max(-.02,Math.min(1.02,p.x+vx));p.y=Math.max(.02,Math.min(.99,p.y+vy));
  p.sp=Math.hypot(vx,vy)/SP;if(Math.abs(vx)>.0003)p.f=vx>0?1:-1;p.ph+=p.sp*.55;
}
function decide(p){
  const t=hold.t,att=t==0?p.x>.6:p.x<.4;
  if((att&&Math.random()<.5)||Math.random()<.07)shoot();else pass();
}
function pass(){
  const t=hold.t,d=t?-1:1,ks=[1,2,3,4,5].filter(k=>k!==hold.i),k=ks[Math.floor(Math.random()*ks.length)],r=pl[t][k];
  const tx=Math.min(.97,Math.max(.03,r.x+d*.05)),ty=Math.min(.95,Math.max(.05,r.y));
  const dist=Math.hypot(tx-ball.x,(ty-ball.y)*.65);
  fl={sx:ball.x,sy:ball.y,tx:tx,ty:ty,zs:0,ze:0,arc:.12+Math.random()*.25,t:0,dur:Math.max(10,Math.round(10+dist*70)),shot:false,rec:{t:t,i:k},by:t};
  st='fly';
}
function shoot(){
  const t=hold.t,d=t?-1:1,gx=t==0?1:0,r=Math.random();let o,ty,ze,tx=gx+d*.012;
  if(r<.38){o='goal';ty=.5+(Math.random()-.5)*.09;ze=.2+Math.random()*.9}
  else if(r<.75){o='save';ty=.5+(Math.random()-.5)*.07;ze=.4+Math.random()*.4;tx=gx-d*.03}
  else{o='miss';ty=.5+(Math.random()<.5?-1:1)*(.08+Math.random()*.06);ze=Math.random()<.5?1.8:.5}
  fl={sx:ball.x,sy:ball.y,tx:tx,ty:ty,zs:.1,ze:ze,arc:.1,t:0,dur:Math.max(10,Math.round(8+Math.abs(gx-ball.x)*38)),shot:true,o:o,by:t,rec:null};
  st='fly';cm('Shoots!');
}
function land(){
  const t=fl.by;
  if(!fl.shot){
    if(Math.random()<.16){
      const ot=1-t;let bi=1,bd=9;
      for(let i=1;i<6;i++){const q=pl[ot][i],dd=Math.hypot(q.x-fl.tx,q.y-fl.ty);if(dd<bd){bd=dd;bi=i}}
      hold={t:ot,i:bi};poss=ot;carryT=14+Math.random()*10;cm('Intercepted!');
    }else{hold={t:t,i:fl.rec.i};carryT=16+Math.random()*24}
    st='carry';fl=null;return;
  }
  if(fl.o==='goal'){
    score[t]++;scorer={t:t,p:pl[t][hold.i]};st='cel';celT=95;flashT=14;cm('GOAL!');
  }else{
    const ot=1-t;hold={t:ot,i:0};poss=ot;carryT=28;st='carry';cm(fl.o==='save'?'What a save!':'Just wide!');
  }
  fl=null;
}
function step(){
  if(ft)return;
  const ox=ball.x,oy=ball.y;
  if(st==='carry'){
    const p=pl[hold.t][hold.i],d=hold.t?-1:1;
    moveTo(p,Math.min(.97,Math.max(.03,p.x+d*.05)),p.y+(.5-p.y)*.15,SP*.75);
    ball.x=p.x+p.f*.011;ball.y=p.y+.002;ball.z=0;
    if(--carryT<=0)decide(p);
  }else if(st==='fly'){
    fl.t++;const u=Math.min(1,fl.t/fl.dur);
    ball.x=fl.sx+(fl.tx-fl.sx)*u;ball.y=fl.sy+(fl.ty-fl.sy)*u;
    ball.z=fl.zs+(fl.ze-fl.zs)*u+fl.arc*Math.sin(Math.PI*u);
    if(fl.t>=fl.dur)land();
  }else if(st==='cel'){
    ball.z*=.9;if(--celT<=0)kickoff(1-scorer.t);
  }
  rot+=Math.hypot(ball.x-ox,ball.y-oy)*60;
  let pr=-1,bd=9;
  for(let i=1;i<6;i++){const q=pl[1-poss][i],dd=Math.hypot(q.x-ball.x,q.y-ball.y);if(dd<bd){bd=dd;pr=i}}
  for(let t=0;t<2;t++)for(let i=0;i<6;i++){
    const p=pl[t][i];
    if(st==='carry'&&hold.t===t&&hold.i===i)continue;
    if(st==='cel'){
      if(t===scorer.t){
        p.cel=true;
        if(p!==scorer.p)moveTo(p,scorer.p.x+(i-2.5)*.012,scorer.p.y+(i%3-1)*.05,SP*.9);else p.sp*=.8;
      }else moveTo(p,p.x,p.y,0);
      continue;
    }
    p.cel=false;let sp=SP*.7,tx,ty;
    if(st==='fly'&&fl.rec&&fl.rec.t===t&&fl.rec.i===i){tx=fl.tx;ty=fl.ty;sp=SP*.95}
    else if(i===0){
      tx=p.hx;ty=.5+(ball.y-.5)*.25;sp=SP*.4;
      if(st==='fly'&&fl.shot&&t===1-fl.by){ty=fl.ty;sp=SP*.9}
      ty=Math.max(.43,Math.min(.57,ty));
    }else if(t!==poss&&i===pr){tx=ball.x;ty=ball.y;sp=SP*.8}
    else{const d=t?-1:1,off=(t===poss?.1:-.05)*d;tx=p.hx+(ball.x-p.hx)*.3+off;ty=p.hy+(ball.y-p.hy)*.25}
    moveTo(p,tx,ty,sp);
  }
  moveTo(ref,ball.x*.85+.075,ball.y>.5?.2:.82,SP*.55);
}

// ---------- drawing ----------
function drawP(p,t){
  const q=P(p.x,p.y),h=PH()*q.s,x=q.x,y=q.y,f=p.f,m=Math.min(1,p.sp);
  const T=t===2?null:(t?B:A);
  const kit=t===2?'#fde047':p.gk?(p.t?'#16a34a':'#eab308'):T.kit;
  const sh=(t===2||p.gk)?'#111827':T.sh,so=(t===2||p.gk)?'#111827':T.so;
  g.fillStyle='rgba(0,0,0,.38)';g.beginPath();g.ellipse(x,y,h*.3,h*.075,0,0,7);g.fill();
  const sw=Math.sin(p.ph),hy=y-h*.44;g.lineCap='round';
  for(let s=-1;s<=1;s+=2){
    const hx=x+s*h*.055,fx=hx+(p.cel?0:sw*s*h*.24*m*f),fy=y-Math.max(0,Math.cos(p.ph)*s)*h*.1*m;
    const kx=(hx+fx)/2+f*h*.04*m,ky=(hy+fy)/2;
    line2(hx,hy,kx,ky,h*.12,sh);line2(kx,ky,fx,fy,h*.1,so);
    g.fillStyle='#0b0b0b';g.beginPath();g.ellipse(fx+f*h*.04,fy,h*.075,h*.04,0,0,7);g.fill();
  }
  const tw=h*.31,ty=y-h*.8,th=h*.38;
  g.fillStyle=kit;rr(x-tw/2,ty,tw,th,h*.07);g.fill();
  g.fillStyle='rgba(0,0,0,.2)';rr(x,ty,tw/2,th,h*.07);g.fill();
  g.fillStyle=sh;rr(x-tw/2,y-h*.47,tw,h*.1,h*.04);g.fill();
  for(let s=-1;s<=1;s+=2){
    const sx=x+s*h*.17,sy=y-h*.74;let hx2,hy2;
    if(p.cel){hx2=sx+s*h*.1;hy2=sy-h*.22}else{hx2=sx-sw*s*h*.14*m*f;hy2=sy+h*.24-m*h*.04}
    const ex=(sx+hx2)/2+s*h*.03,ey=(sy+hy2)/2+h*.02;
    line2(sx,sy,ex,ey,h*.095,kit);line2(ex,ey,hx2,hy2,h*.08,p.sk);
  }
  const hx3=x+f*h*.015,hy3=y-h*.9,r=h*.1;
  g.fillStyle=p.sk;g.beginPath();g.arc(hx3,hy3,r,0,7);g.fill();
  g.fillStyle=p.hr;g.beginPath();g.arc(hx3,hy3,r*1.03,Math.PI*1.05,Math.PI*1.95);g.closePath();g.fill();
  if(h>26&&p.num!==''){
    g.fillStyle=lum(kit)>.6?'#111':'#fff';g.font='bold '+(h*.16)+'px sans-serif';
    g.textAlign='center';g.textBaseline='middle';g.fillText(String(p.num),x,y-h*.6);
  }
}
function drawBall(){
  const q=P(ball.x,ball.y,ball.z),gq=P(ball.x,ball.y,0),r=H*.017*gq.s;
  g.fillStyle='rgba(0,0,0,'+Math.max(.15,.4-ball.z*.12)+')';g.beginPath();g.ellipse(gq.x,gq.y,r*1.1,r*.35,0,0,7);g.fill();
  const cy=q.y-r,gr=g.createRadialGradient(q.x-r*.3,cy-r*.3,r*.1,q.x,cy,r);
  gr.addColorStop(0,'#fff');gr.addColorStop(1,'#cbd5e1');
  g.fillStyle=gr;g.beginPath();g.arc(q.x,cy,r,0,7);g.fill();
  g.fillStyle='#1f2937';
  for(let k=0;k<3;k++){const a=rot+k*2.1;g.beginPath();g.arc(q.x+Math.cos(a)*r*.5,cy+Math.sin(a)*r*.4,r*.27,0,7);g.fill()}
  g.strokeStyle='rgba(0,0,0,.45)';g.lineWidth=1;g.beginPath();g.arc(q.x,cy,r,0,7);g.stroke();
}
function goal(side){
  const x0=side?1:0,d=side?1:-1,y1=.446,y2=.554,zt=1.36,bx=x0+d*.022,zb=1.2;
  g.strokeStyle='rgba(255,255,255,.3)';g.lineWidth=Math.max(1,H*.003);
  for(let k=0;k<=10;k++){const y=y1+(y2-y1)*k/10;ln(P(bx,y,0),P(bx,y,zb))}
  for(let k=0;k<=6;k++){const z=zb*k/6;ln(P(bx,y1,z),P(bx,y2,z))}
  for(let k=0;k<=4;k++){ln(P(x0,y1,zt*k/4),P(bx,y1,zb*k/4));ln(P(x0,y2,zt*k/4),P(bx,y2,zb*k/4))}
  for(let k=0;k<=8;k++){const y=y1+(y2-y1)*k/8;ln(P(x0,y,zt),P(bx,y,zb))}
  g.strokeStyle='#fff';g.lineWidth=Math.max(2,H*.008);
  ln(P(x0,y1,0),P(x0,y1,zt));ln(P(x0,y1,zt),P(x0,y2,zt));ln(P(x0,y2,zt),P(x0,y2,0));
}
function poly(pts,fill){g.beginPath();pts.forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.closePath();g.fillStyle=fill;g.fill()}
function path(pts){g.beginPath();pts.forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.stroke()}
function pitch(){
  g.fillStyle='#1f6f35';g.fillRect(0,TOP()-H*.05,W,H);
  for(let k=0;k<20;k++){const x0=-.5+k*.1;
    poly([P(x0,-.1),P(x0+.1,-.1),P(x0+.1,1.3),P(x0,1.3)],k%2?'#2b8a42':'#34a04c')}
  g.strokeStyle='rgba(255,255,255,.88)';g.lineWidth=Math.max(2,H*.007);g.lineJoin='round';
  path([P(0,0),P(1,0),P(1,1),P(0,1),P(0,0)]);
  ln(P(.5,0),P(.5,1));
  const ci=[];for(let a=0;a<=64;a++){const t=a/64*Math.PI*2;ci.push(P(.5+.087*Math.cos(t),.5+.135*Math.sin(t)))}
  path(ci);
  path([P(0,.25),P(.15,.25),P(.15,.75),P(0,.75)]);path([P(1,.25),P(.85,.25),P(.85,.75),P(1,.75)]);
  path([P(0,.39),P(.05,.39),P(.05,.61),P(0,.61)]);path([P(1,.39),P(.95,.39),P(.95,.61),P(1,.61)]);
  const sp=P(.5,.5);g.fillStyle='#fff';g.beginPath();g.ellipse(sp.x,sp.y,H*.006,H*.003,0,0,7);g.fill();
}
function hud(){
  const bx=W*.025,by=H*.045,bw=W*.5,bh=H*.105;
  g.fillStyle='rgba(8,12,28,.88)';rr(bx,by,bw,bh,bh*.25);g.fill();
  [[A,.03],[B,.935]].forEach(a=>{g.fillStyle=a[0].kit;g.fillRect(bx+bw*a[1],by+bh*.2,bw*.03,bh*.6);
    g.strokeStyle='rgba(255,255,255,.6)';g.lineWidth=1;g.strokeRect(bx+bw*a[1],by+bh*.2,bw*.03,bh*.6)});
  g.fillStyle='#fff';g.textBaseline='middle';g.font='800 '+(H*.058)+'px sans-serif';
  g.textAlign='left';g.fillText(A.c,bx+bw*.09,by+bh*.54);
  g.textAlign='right';g.fillText(B.c,bx+bw*.91,by+bh*.54);
  g.textAlign='center';g.fillStyle='#ffd43b';g.fillText(score[0]+' - '+score[1],bx+bw*.5,by+bh*.54);
  const cx=bx+bw+W*.012,cw=W*.13;
  g.fillStyle='rgba(8,12,28,.88)';rr(cx,by,cw,bh,bh*.25);g.fill();
  g.fillStyle='#fff';g.font='700 '+(H*.052)+'px sans-serif';g.fillText(min>=90?'FT':min+"'",cx+cw/2,by+bh*.54);
  const lw=W*.2,lx=W*.975-lw;
  g.fillStyle='rgba(8,12,28,.88)';rr(lx,by,lw,bh*.72,bh*.2);g.fill();
  g.fillStyle=(fr%30<20)?'#ef4444':'#7f1d1d';g.beginPath();g.arc(lx+lw*.1,by+bh*.36,bh*.1,0,7);g.fill();
  g.fillStyle='#fff';g.font='700 '+(H*.036)+'px sans-serif';g.textAlign='left';g.fillText('LIVE · VIRTUAL',lx+lw*.2,by+bh*.37);
  if(cmT>0){
    g.globalAlpha=Math.min(1,cmT/20);g.font='800 '+(H*.06)+'px sans-serif';
    const tw=g.measureText(cmTxt).width+H*.1;
    g.fillStyle='rgba(8,12,28,.85)';rr(W/2-tw/2,H*.87,tw,H*.093,H*.045);g.fill();
    g.fillStyle='#fff';g.textAlign='center';g.fillText(cmTxt,W/2,H*.917);g.globalAlpha=1;
  }
}
function draw(){
  if(!W)return;
  let gr=g.createLinearGradient(0,0,0,H*.43);gr.addColorStop(0,'#050a1c');gr.addColorStop(1,'#16224a');
  g.fillStyle=gr;g.fillRect(0,0,W,H);
  g.drawImage(stands,-W*.5-(cam-.5)*W*.35,H*.05);
  [[.1,.05],[.9,.05]].forEach(l=>{const r=g.createRadialGradient(W*l[0],H*l[1],0,W*l[0],H*l[1],H*.35);
    r.addColorStop(0,'rgba(255,255,235,.55)');r.addColorStop(1,'rgba(255,255,235,0)');g.fillStyle=r;g.fillRect(0,0,W,H*.5)});
  for(let k=0;k<2;k++)if(Math.random()<.35){const x=Math.random()*W,y=H*.1+Math.random()*H*.22,r=H*.012;
    g.fillStyle='rgba(255,255,255,.95)';g.beginPath();g.arc(x,y,r*.4,0,7);g.fill();
    g.strokeStyle='rgba(255,255,255,.7)';g.lineWidth=1;g.beginPath();g.moveTo(x-r,y);g.lineTo(x+r,y);g.moveTo(x,y-r);g.lineTo(x,y+r);g.stroke()}
  const st2=W*.42,sc=cam*W*1.75*.62,idx=Math.floor(sc/st2),off=-(sc%st2);
  for(let k=-1;k<4;k++){const x=off+k*st2;g.fillStyle=(((idx+k)%2)+2)%2?'#0ea5e9':'#f97316';
    g.fillRect(x,H*.335,st2-3,H*.048);g.fillStyle='#fff';g.font='800 '+(H*.03)+'px sans-serif';
    g.textAlign='center';g.textBaseline='middle';g.fillText('SCORE PREDICTOR',x+st2/2,H*.359)}
  pitch();goal(0);goal(1);
  const items=[];
  pl.forEach((tm,t)=>tm.forEach(p=>items.push({y:p.y,f:()=>drawP(p,t)})));
  items.push({y:ref.y,f:()=>drawP(ref,2)});items.push({y:ball.y+.0001,f:drawBall});
  items.sort((a,b)=>a.y-b.y);items.forEach(o=>o.f());
  const v=g.createRadialGradient(W/2,H*.55,H*.3,W/2,H*.55,H*.95);
  v.addColorStop(0,'rgba(0,0,0,0)');v.addColorStop(1,'rgba(0,0,0,.5)');g.fillStyle=v;g.fillRect(0,0,W,H);
  if(st==='cel'){
    if(fr%2==0)for(let k=0;k<3;k++)cf.push({x:Math.random()*W,y:-5,vx:(Math.random()-.5)*3,vy:3+Math.random()*4,
      c:['#fde047','#f43f5e','#38bdf8','#fff','#4ade80'][Math.floor(Math.random()*5)]});
    const s=1+.07*Math.sin(fr*.3),sz=H*.2*s;
    g.font='900 '+sz+'px sans-serif';g.textAlign='center';g.textBaseline='middle';
    g.lineWidth=H*.014;g.strokeStyle='rgba(120,0,0,.9)';g.strokeText('GOAL!',W/2,H*.3);
    const gg=g.createLinearGradient(0,H*.2,0,H*.4);gg.addColorStop(0,'#fff7ae');gg.addColorStop(1,'#f59e0b');
    g.fillStyle=gg;g.fillText('GOAL!',W/2,H*.3);
  }
  cf=cf.filter(q=>q.y<H);cf.forEach(q=>{q.x+=q.vx;q.y+=q.vy;g.fillStyle=q.c;g.fillRect(q.x,q.y,H*.012,H*.02)});
  if(flashT>0){g.fillStyle='rgba(255,255,255,'+(flashT/14*.35)+')';g.fillRect(0,0,W,H)}
  hud();
  if(ft){
    g.fillStyle='rgba(0,0,0,.55)';g.fillRect(0,0,W,H);g.fillStyle='#fff';g.textAlign='center';g.textBaseline='middle';
    g.font='900 '+(H*.12)+'px sans-serif';g.fillText('FULL TIME',W/2,H*.42);
    g.font='800 '+(H*.09)+'px sans-serif';g.fillStyle='#ffd43b';g.fillText(A.c+' '+score[0]+' - '+score[1]+' '+B.c,W/2,H*.6);
  }
}
setInterval(()=>{
  step();
  if(ball&&st!=='cel'){cam+=(Math.max(.24,Math.min(.76,ball.x))-cam)*.06}else if(ball){cam+=(Math.max(.24,Math.min(.76,ball.x))-cam)*.03}
  draw();fr++;if(cmT>0)cmT--;if(flashT>0)flashT--;
},33);
setInterval(()=>{if(!ft){if(min<90)min++;else{ft=true}}else if(++ftWait>5){start()}},700);
fit();addEventListener('resize',()=>{fit()});start();
</script>
"""

VIRTUAL_HTML_3D_TEMPLATE = """
<style>
 html,body{margin:0;background:transparent;overflow:hidden}
 #w{position:fixed;inset:0;overflow:hidden;background:#050a1c;
    --u:5px;font-family:'Arial Black',Impact,Arial,sans-serif;font-style:italic;color:#fff}
 canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
 #sb{position:absolute;left:2.5%;top:64px;display:flex;gap:calc(var(--u)*.8)}
 .box{background:rgba(8,12,28,.88);border-radius:calc(var(--u)*1);padding:calc(var(--u)*.8) calc(var(--u)*1.5);
      display:flex;align-items:center;gap:calc(var(--u)*1.1);font-size:calc(var(--u)*3.3);line-height:1}
 .chip{display:inline-block;width:calc(var(--u)*1.1);height:calc(var(--u)*3.4);border-radius:2px;border:1px solid rgba(255,255,255,.6)}
 .sc{color:#ffd43b}
 #live{position:absolute;right:2.5%;top:64px;background:rgba(8,12,28,.88);border-radius:calc(var(--u)*1);
       padding:calc(var(--u)*.9) calc(var(--u)*1.5);font-size:calc(var(--u)*2.5);display:flex;align-items:center;gap:calc(var(--u)*.8)}
 #live i{display:inline-block;width:calc(var(--u)*1.5);height:calc(var(--u)*1.5);border-radius:50%;background:#ef4444;animation:bl 1s infinite}
 @keyframes bl{50%{opacity:.25}}
 #cm{position:absolute;left:50%;top:calc(64px + var(--u)*8);transform:translateX(-50%);background:rgba(8,12,28,.88);opacity:0;
     border-radius:calc(var(--u)*3);padding:calc(var(--u)*.9) calc(var(--u)*3);font-size:calc(var(--u)*3.6);white-space:nowrap}
 #goal{position:absolute;left:0;right:0;top:14%;text-align:center;font-size:calc(var(--u)*17);color:#ffe066;display:none;
       -webkit-text-stroke:calc(var(--u)*.6) #7a0a0a;text-shadow:0 calc(var(--u)*.8) calc(var(--u)*2) rgba(0,0,0,.7);
       animation:pop .45s infinite alternate}
 @keyframes pop{from{transform:scale(.94)}to{transform:scale(1.07)}}
 #ftb{position:absolute;inset:0;background:rgba(0,0,0,.6);display:none;flex-direction:column;align-items:center;
      justify-content:center;font-size:calc(var(--u)*9);gap:calc(var(--u)*1.5)}
 #ftb span{color:#ffd43b;font-size:calc(var(--u)*6.5)}
</style>
<div id="w">
 <canvas id="c"></canvas>
 <div id="sb"><div class="box"><span class="chip" id="chA"></span><span id="nA"></span><span class="sc" id="sco">0 - 0</span><span id="nB"></span><span class="chip" id="chB"></span></div><div class="box" id="clk">0'</div></div>
 <div id="live"><i></i>LIVE · VIRTUAL</div>
 <div id="goal">GOAL!</div>
 <div id="cm"></div>
 <div id="ftb"><b>FULL TIME</b><span id="ftsc"></span></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const FALLBACK=__FALLBACK__;
function syncTheme(){
  try{
    const d=window.parent.document,app=d.querySelector('.stApp')||d.body;
    const m=getComputedStyle(app).color.match(/[0-9.]+/g),l=(m[0]*.3+m[1]*.59+m[2]*.11)/255;
    d.documentElement.style.setProperty('--sheet-bg',l<.5?'rgba(255,255,255,.97)':'rgba(14,17,23,.97)');
  }catch(e){}
}
syncTheme();setInterval(syncTheme,1500);
(function(){
function fallback(){try{document.open();document.write(FALLBACK);document.close()}catch(e){}}
if(typeof THREE==='undefined'){fallback();return}
try{
const canvas=document.getElementById('c'),wrap=document.getElementById('w');
const renderer=new THREE.WebGLRenderer({canvas:canvas,antialias:true,powerPreference:'high-performance'});
if(!renderer.getContext()){fallback();return}
const L=84,WD=44,GW=9,GH=4.6,SC=1.9,PHM=3.4,SP=.0042;
const WX=x=>(x-.5)*L,WZ=y=>(y-.5)*WD;
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));
renderer.outputEncoding=THREE.sRGBEncoding;
renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
const scene=new THREE.Scene();scene.background=new THREE.Color(0x070c22);scene.fog=new THREE.Fog(0x070c22,75,190);
const camera=new THREE.PerspectiveCamera(40,16/9,.5,400);
scene.add(new THREE.HemisphereLight(0xcfe0ff,0x1f4a2a,.8));
const sun=new THREE.DirectionalLight(0xfff3dc,1.15);sun.position.set(28,65,30);sun.castShadow=true;
sun.shadow.mapSize.set(1024,1024);
const sc2=sun.shadow.camera;sc2.left=-62;sc2.right=62;sc2.top=42;sc2.bottom=-42;sc2.near=10;sc2.far=150;sun.shadow.bias=-.0006;
scene.add(sun);scene.add(sun.target);

// ---------- helpers ----------
function mkCv(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c}
function ctex(cv){const t=new THREE.CanvasTexture(cv);t.encoding=THREE.sRGBEncoding;t.anisotropy=4;return t}
const matCache={};
function mat(col,r){const k=col+'|'+r;if(!matCache[k])matCache[k]=new THREE.MeshStandardMaterial({color:col,roughness:r==null?.85:r});return matCache[k]}
function lum(h){const n=parseInt(h.slice(1),16);return (((n>>16)&255)*.3+((n>>8)&255)*.59+(n&255)*.11)/255}

// ---------- pitch ----------
(function(){
  const ppm=24,cv=mkCv(L*ppm,WD*ppm),x=cv.getContext('2d'),m=v=>v*ppm,n=14,sw=cv.width/n;
  for(let i=0;i<n;i++){x.fillStyle=i%2?'#2f8f45':'#3aa653';x.fillRect(i*sw,0,sw+1,cv.height)}
  for(let i=0;i<9000;i++){x.fillStyle='rgba(0,0,0,'+Math.random()*.06+')';x.fillRect(Math.random()*cv.width,Math.random()*cv.height,2,2)}
  x.strokeStyle='rgba(255,255,255,.92)';x.fillStyle='#fff';x.lineWidth=4;
  x.strokeRect(3,3,cv.width-6,cv.height-6);
  x.beginPath();x.moveTo(cv.width/2,0);x.lineTo(cv.width/2,cv.height);x.stroke();
  x.beginPath();x.arc(cv.width/2,cv.height/2,m(7),0,7);x.stroke();
  x.beginPath();x.arc(cv.width/2,cv.height/2,5,0,7);x.fill();
  const a=Math.acos(4.5/8),cy=cv.height/2;
  [0,1].forEach(s=>{
    const dir=s?-1:1,ox=s?cv.width:0;
    x.strokeRect(s?cv.width-m(14):0,cy-m(13),m(14),m(26));
    x.strokeRect(s?cv.width-m(5):0,cy-m(6.5),m(5),m(13));
    x.beginPath();x.arc(ox+dir*m(9.5),cy,5,0,7);x.fill();
    x.beginPath();
    if(s)x.arc(ox+dir*m(9.5),cy,m(8),Math.PI-a,Math.PI+a);else x.arc(ox+dir*m(9.5),cy,m(8),-a,a);
    x.stroke();
  });
  const pm=new THREE.Mesh(new THREE.PlaneGeometry(L,WD),new THREE.MeshStandardMaterial({map:ctex(cv),roughness:1}));
  pm.rotation.x=-Math.PI/2;pm.receiveShadow=true;scene.add(pm);
  const ap=new THREE.Mesh(new THREE.PlaneGeometry(220,150),new THREE.MeshStandardMaterial({color:0x1a5a2c,roughness:1}));
  ap.rotation.x=-Math.PI/2;ap.position.y=-.03;ap.receiveShadow=true;scene.add(ap);
})();

// ---------- stadium ----------
function crowdTex(){
  const cv=mkCv(1024,512),x=cv.getContext('2d');x.fillStyle='#10162e';x.fillRect(0,0,1024,512);
  const cols=['#e5484d','#3b82f6','#f1f5f9','#fbbf24','#94a3b8','#22c55e','#1e293b','#a855f7'];
  for(let i=0;i<7000;i++){x.fillStyle=cols[Math.floor(Math.random()*cols.length)];x.globalAlpha=.5+Math.random()*.5;
    x.beginPath();x.arc(Math.random()*1024,Math.random()*512,2+Math.random()*3,0,7);x.fill()}
  x.globalAlpha=1;const t=ctex(cv);t.wrapS=t.wrapT=THREE.RepeatWrapping;return t;
}
const crowdTexs=[];
function stand(px,pz,w,yaw){
  const grp=new THREE.Group();grp.position.set(px,0,pz);grp.rotation.y=yaw;
  const t=crowdTex();t.repeat.set(w/30,1);crowdTexs.push(t);
  const pl=new THREE.Mesh(new THREE.PlaneGeometry(w,22),new THREE.MeshBasicMaterial({map:t,color:0xb8b8c8}));
  pl.rotation.x=-.95;pl.position.y=8;grp.add(pl);scene.add(grp);
}
stand(0,-WD/2-12,170,0);stand(-(L/2+13),0,WD+60,Math.PI/2);stand(L/2+13,0,WD+60,-Math.PI/2);
(function(){const w=new THREE.Mesh(new THREE.PlaneGeometry(400,70),new THREE.MeshBasicMaterial({color:0x070c22}));
  w.position.set(0,25,-52);scene.add(w)})();
function adTex(){
  const cv=mkCv(2048,128),x=cv.getContext('2d'),cols=['#0ea5e9','#f97316','#22c55e','#e11d48'];
  for(let i=0;i<4;i++){x.fillStyle=cols[i];x.fillRect(i*512,0,512,128);x.fillStyle='#fff';x.font='900 64px Arial';
    x.textAlign='center';x.textBaseline='middle';x.fillText('SCORE PREDICTOR',i*512+256,68)}
  const t=ctex(cv);t.wrapS=THREE.RepeatWrapping;return t;
}
function board(len,px,pz,yaw){
  const t=adTex();t.repeat.set(len/40,1);
  const b=new THREE.Mesh(new THREE.PlaneGeometry(len,1.4),new THREE.MeshBasicMaterial({map:t}));
  b.position.set(px,.8,pz);b.rotation.y=yaw;scene.add(b);
}
board(L+26,0,-WD/2-2.3,0);board(WD+10,-(L/2+4.5),0,Math.PI/2);board(WD+10,L/2+4.5,0,-Math.PI/2);
(function(){
  const cv=mkCv(128,128),x=cv.getContext('2d'),gr=x.createRadialGradient(64,64,0,64,64,64);
  gr.addColorStop(0,'rgba(255,255,240,1)');gr.addColorStop(.3,'rgba(255,255,220,.45)');gr.addColorStop(1,'rgba(255,255,220,0)');
  x.fillStyle=gr;x.fillRect(0,0,128,128);const gt=new THREE.CanvasTexture(cv);
  [[-54,-32],[54,-32],[-54,32],[54,32]].forEach(p=>{
    const mast=new THREE.Mesh(new THREE.CylinderGeometry(.5,.8,34,8),new THREE.MeshStandardMaterial({color:0x2a2f45}));
    mast.position.set(p[0],17,p[1]);scene.add(mast);
    const head=new THREE.Mesh(new THREE.BoxGeometry(9,4,1),new THREE.MeshBasicMaterial({color:0xffffff}));
    head.position.set(p[0],35,p[1]);scene.add(head);
    const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:gt,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true}));
    sp.scale.set(46,46,1);sp.position.set(p[0],35,p[1]);scene.add(sp);
  });
})();

// ---------- goals ----------
function netMat(rx,ry){
  const cv=mkCv(64,64),x=cv.getContext('2d');x.strokeStyle='rgba(255,255,255,.9)';x.lineWidth=3;
  x.strokeRect(0,0,64,64);const t=new THREE.CanvasTexture(cv);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(rx,ry);
  return new THREE.MeshBasicMaterial({map:t,transparent:true,opacity:.55,side:THREE.DoubleSide,depthWrite:false});
}
function makeGoal(side){
  const dir=side?1:-1,g=new THREE.Group();g.position.set(dir*L/2,0,0);
  const pm=mat('#ffffff',.4);
  [-GW/2,GW/2].forEach(z=>{const p=new THREE.Mesh(new THREE.CylinderGeometry(.13,.13,GH,10),pm);p.position.set(0,GH/2,z);p.castShadow=true;g.add(p)});
  const bar=new THREE.Mesh(new THREE.CylinderGeometry(.13,.13,GW,10),pm);bar.rotation.x=Math.PI/2;bar.position.set(0,GH,0);bar.castShadow=true;g.add(bar);
  const back=new THREE.Mesh(new THREE.PlaneGeometry(GW,3.8),netMat(GW*1.2,4));back.rotation.y=Math.PI/2;back.position.set(dir*3,1.9,0);g.add(back);
  [-GW/2,GW/2].forEach(z=>{const s=new THREE.Mesh(new THREE.PlaneGeometry(3,4.2),netMat(4,4));s.position.set(dir*1.5,2.1,z);g.add(s)});
  const top=new THREE.Mesh(new THREE.PlaneGeometry(3,GW),netMat(4,GW*1.2));top.rotation.x=-Math.PI/2;top.position.set(dir*1.5,4.2,0);g.add(top);
  scene.add(g);
}
makeGoal(0);makeGoal(1);

// ---------- players ----------
const GEO={
  short:new THREE.CylinderGeometry(.1,.085,.3,10),shin:new THREE.CylinderGeometry(.065,.065,.5,8),
  boot:new THREE.BoxGeometry(.12,.08,.26),torso:new THREE.CylinderGeometry(.24,.2,.62,14),hip:new THREE.CylinderGeometry(.2,.2,.2,12),
  head:new THREE.SphereGeometry(.115,16,12),hair:new THREE.SphereGeometry(.122,16,8,0,Math.PI*2,0,Math.PI*.52),
  ua:new THREE.CylinderGeometry(.06,.055,.26,8),fa:new THREE.CylinderGeometry(.05,.045,.28,8),hand:new THREE.SphereGeometry(.055,8,6),
  num:new THREE.PlaneGeometry(.34,.34)};
function numTex(n,col){
  const cv=mkCv(64,64),x=cv.getContext('2d');x.fillStyle=col;x.font='bold 46px Arial';x.textAlign='center';x.textBaseline='middle';
  x.fillText(String(n),32,34);return ctex(cv);
}
function buildPlayer(kit,sh,so,sk,hr,num){
  const root=new THREE.Group(),body=new THREE.Group();root.add(body);
  const mK=mat(kit,.7),mS=mat(sh,.8),mO=mat(so,.8),mSk=mat(sk,.7),mH=mat(hr,.9),mB=mat('#0b0b0b',.5);
  function add(par,geo,m,x,y,z,sx,sy,sz){const me=new THREE.Mesh(geo,m);me.position.set(x,y,z);if(sx)me.scale.set(sx,sy,sz);me.castShadow=true;par.add(me);return me}
  const legs=[-1,1].map(s=>{const pv=new THREE.Group();pv.position.set(s*.1,.93,0);body.add(pv);
    add(pv,GEO.short,mS,0,-.15,0);add(pv,GEO.shin,mO,0,-.55,0);add(pv,GEO.boot,mB,0,-.86,.05);return pv});
  add(body,GEO.hip,mS,0,.98,0,1,1,.75);
  add(body,GEO.torso,mK,0,1.24,0,1,1,.62);
  const arms=[-1,1].map(s=>{const pv=new THREE.Group();pv.position.set(s*.29,1.5,0);body.add(pv);
    add(pv,GEO.ua,mK,0,-.13,0);add(pv,GEO.fa,mSk,0,-.4,0);add(pv,GEO.hand,mSk,0,-.56,0);pv.rotation.z=s*.1;return pv});
  add(body,GEO.head,mSk,0,1.7,.01);const hair=add(body,GEO.hair,mH,0,1.705,-.01);hair.rotation.x=-.25;
  let tex=null;
  if(num!==''){tex=numTex(num,lum(kit)>.6?'#111111':'#ffffff');
    const np=new THREE.Mesh(GEO.num,new THREE.MeshBasicMaterial({map:tex,transparent:true}));
    np.position.set(0,1.26,-.16);np.rotation.y=Math.PI;body.add(np)}
  root.scale.set(SC,SC,SC);
  return {root:root,body:body,legL:legs[0],legR:legs[1],armL:arms[0],armR:arms[1],lean:0,tex:tex};
}
// ---------- ball ----------
const ballMesh=(function(){
  const cv=mkCv(512,256),x=cv.getContext('2d');x.fillStyle='#f8fafc';x.fillRect(0,0,512,256);x.fillStyle='#1f2937';
  for(let i=0;i<8;i++)for(let j=0;j<3;j++){x.beginPath();x.arc(i*64+(j%2)*32+16,40+j*80,22,0,7);x.fill()}
  const b=new THREE.Mesh(new THREE.SphereGeometry(.5,24,16),new THREE.MeshStandardMaterial({map:ctex(cv),roughness:.4}));
  b.castShadow=true;scene.add(b);return b;
})();
// ---------- confetti ----------
const NP=180,pp=new Float32Array(NP*3),pc=new Float32Array(NP*3),pvv=new Float32Array(NP*3),plife=new Float32Array(NP);
for(let i=0;i<NP;i++)pp[i*3+1]=-50;
const pg=new THREE.BufferGeometry();pg.setAttribute('position',new THREE.BufferAttribute(pp,3));pg.setAttribute('color',new THREE.BufferAttribute(pc,3));
const pts=new THREE.Points(pg,new THREE.PointsMaterial({size:.55,vertexColors:true}));pts.frustumCulled=false;scene.add(pts);
const CONF=[[1,.88,.28],[.96,.25,.37],[.22,.74,.97],[1,1,1],[.29,.87,.5]];let nextP=0;
function spawn(cx,cz){
  for(let k=0;k<3;k++){const i=nextP=(nextP+1)%NP;
    pp[i*3]=cx+(Math.random()-.5)*10;pp[i*3+1]=7+Math.random()*4;pp[i*3+2]=cz+(Math.random()-.5)*10;
    pvv[i*3]=(Math.random()-.5)*.1;pvv[i*3+1]=-.05-Math.random()*.08;pvv[i*3+2]=(Math.random()-.5)*.1;plife[i]=1;
    const c=CONF[Math.floor(Math.random()*5)];pc[i*3]=c[0];pc[i*3+1]=c[1];pc[i*3+2]=c[2]}
}
function confStep(){
  for(let i=0;i<NP;i++)if(plife[i]>0){pp[i*3]+=pvv[i*3];pp[i*3+1]+=pvv[i*3+1];pp[i*3+2]+=pvv[i*3+2];
    if(pp[i*3+1]<0){plife[i]=0;pp[i*3+1]=-50}}
  pg.attributes.position.needsUpdate=true;pg.attributes.color.needsUpdate=true;
}

// ---------- simulation ----------
const TEAMS=[
 {c:"ARS",kit:"#e11d2e",sh:"#ffffff",so:"#e11d2e"},{c:"CHE",kit:"#1d4ed8",sh:"#1d4ed8",so:"#ffffff"},
 {c:"MCI",kit:"#7dd3fc",sh:"#ffffff",so:"#7dd3fc"},{c:"LIV",kit:"#c8102e",sh:"#c8102e",so:"#c8102e"},
 {c:"BAR",kit:"#7c3aed",sh:"#1e3a8a",so:"#1e3a8a"},{c:"RMA",kit:"#f8fafc",sh:"#f8fafc",so:"#f8fafc"},
 {c:"INT",kit:"#0f4c9c",sh:"#111827",so:"#0f4c9c"},{c:"BAY",kit:"#dc2626",sh:"#ffffff",so:"#dc2626"}];
const SK=['#f1c27d','#e0ac69','#c68642','#8d5524','#5c3a21'],HR=['#161616','#3b2314','#d4a017','#0d0d0d'];
const F0=[[.04,.5],[.2,.3],[.2,.7],[.38,.5],[.55,.32],[.55,.68]],NUM=[1,4,5,8,9,10];
let A,B,score,min,ft,ftWait,pl,ref,ball,poss,st,hold,carryT,fl,celT,cmT=0,cmTxt='',scorer,fr=0,actors=[];
let cp=[0,14,27],cl=[0,0,1];
function mk(t){return F0.map((f,i)=>({t:t,gk:i==0,x:t?1-f[0]:f[0],y:f[1],hx:t?1-f[0]:f[0],hy:f[1],f:t?-1:1,vx:0,vy:0,
  ph:Math.random()*6,sp:0,num:NUM[i],sk:SK[Math.floor(Math.random()*5)],hr:HR[Math.floor(Math.random()*4)],cel:false,kick:0}))}
function buildActors(){
  actors.forEach(a=>{scene.remove(a.root);if(a.tex)a.tex.dispose()});actors=[];
  pl.forEach((tm,t)=>tm.forEach(p=>{const T=t?B:A;
    p.o=buildPlayer(p.gk?(t?'#16a34a':'#eab308'):T.kit,p.gk?'#111827':T.sh,p.gk?'#111827':T.so,p.sk,p.hr,p.num);
    scene.add(p.o.root);actors.push(p.o)}));
  ref.o=buildPlayer('#fde047','#111827','#111827',ref.sk,ref.hr,'');scene.add(ref.o.root);actors.push(ref.o);
}
function start(){
  let i=Math.floor(Math.random()*8),j;do{j=Math.floor(Math.random()*8)}while(j==i);
  A=TEAMS[i];B=TEAMS[j];score=[0,0];min=0;ft=false;ftWait=0;
  pl=[mk(0),mk(1)];
  ref={x:.5,y:.8,f:1,vx:0,vy:0,ph:0,sp:0,sk:SK[1],hr:HR[0],num:'',cel:false,kick:0};
  buildActors();kickoff(0);cm('Kick off!');
  document.getElementById('chA').style.background=A.kit;document.getElementById('chB').style.background=B.kit;
  document.getElementById('nA').textContent=A.c;document.getElementById('nB').textContent=B.c;
}
function cm(t){cmTxt=t;cmT=75}
function kickoff(t){
  pl.forEach(tm=>tm.forEach(p=>{p.x=p.hx;p.y=p.hy;p.cel=false;p.sp=0}));
  poss=t;hold={t:t,i:3};const p=pl[t][3];p.x=.5+(t?.012:-.012);p.y=.5;
  ball={x:.5,y:.5,z:0};st='carry';carryT=30;fl=null;
}
function moveTo(p,tx,ty,sp){
  const dx=tx-p.x,dy=ty-p.y,d=Math.hypot(dx,dy);let vx=0,vy=0;
  if(d>.003){const m=Math.min(sp,d);vx=dx/d*m;vy=dy/d*m}
  p.x=Math.max(-.02,Math.min(1.02,p.x+vx));p.y=Math.max(.02,Math.min(.99,p.y+vy));p.vx=vx;p.vy=vy;
  p.sp=Math.hypot(vx,vy)/SP;if(Math.abs(vx)>.0003)p.f=vx>0?1:-1;p.ph+=p.sp*.7;
}
function decide(p){
  const t=hold.t,att=t==0?p.x>.6:p.x<.4;
  if((att&&Math.random()<.5)||Math.random()<.07)shoot();else pass();
}
function pass(){
  const t=hold.t,d=t?-1:1,ks=[1,2,3,4,5].filter(k=>k!==hold.i),k=ks[Math.floor(Math.random()*ks.length)],r=pl[t][k];
  const tx=Math.min(.97,Math.max(.03,r.x+d*.05)),ty=Math.min(.95,Math.max(.05,r.y));
  const dist=Math.hypot(tx-ball.x,(ty-ball.y)*.65);
  fl={sx:ball.x,sy:ball.y,tx:tx,ty:ty,zs:0,ze:0,arc:.12+Math.random()*.25,t:0,dur:Math.max(10,Math.round(10+dist*70)),shot:false,rec:{t:t,i:k},by:t};
  pl[hold.t][hold.i].kick=8;st='fly';
}
function shoot(){
  const t=hold.t,d=t?-1:1,gx=t==0?1:0,r=Math.random();let o,ty,ze,tx=gx+d*.012;
  if(r<.38){o='goal';ty=.5+(Math.random()-.5)*.09;ze=.2+Math.random()*.9}
  else if(r<.75){o='save';ty=.5+(Math.random()-.5)*.07;ze=.4+Math.random()*.4;tx=gx-d*.03}
  else{o='miss';ty=.5+(Math.random()<.5?-1:1)*(.12+Math.random()*.05);ze=Math.random()<.5?1.8:.5}
  fl={sx:ball.x,sy:ball.y,tx:tx,ty:ty,zs:.1,ze:ze,arc:.1,t:0,dur:Math.max(10,Math.round(8+Math.abs(gx-ball.x)*38)),shot:true,o:o,by:t,rec:null};
  pl[hold.t][hold.i].kick=8;st='fly';cm('Shoots!');
}
function land(){
  const t=fl.by;
  if(!fl.shot){
    if(Math.random()<.16){
      const ot=1-t;let bi=1,bd=9;
      for(let i=1;i<6;i++){const q=pl[ot][i],dd=Math.hypot(q.x-fl.tx,q.y-fl.ty);if(dd<bd){bd=dd;bi=i}}
      hold={t:ot,i:bi};poss=ot;carryT=14+Math.random()*10;cm('Intercepted!');
    }else{hold={t:t,i:fl.rec.i};carryT=16+Math.random()*24}
    st='carry';fl=null;return;
  }
  if(fl.o==='goal'){score[t]++;scorer={t:t,p:pl[t][hold.i]};st='cel';celT=95;cm('GOAL!')}
  else{const ot=1-t;hold={t:ot,i:0};poss=ot;carryT=28;st='carry';cm(fl.o==='save'?'What a save!':'Just wide!')}
  fl=null;
}
function step(){
  if(ft)return;
  if(st==='carry'){
    const p=pl[hold.t][hold.i],d=hold.t?-1:1;
    moveTo(p,Math.min(.97,Math.max(.03,p.x+d*.05)),p.y+(.5-p.y)*.15,SP*.75);
    ball.x=p.x+p.f*.011;ball.y=p.y+.002;ball.z=0;
    if(--carryT<=0)decide(p);
  }else if(st==='fly'){
    fl.t++;const u=Math.min(1,fl.t/fl.dur);
    ball.x=fl.sx+(fl.tx-fl.sx)*u;ball.y=fl.sy+(fl.ty-fl.sy)*u;
    ball.z=fl.zs+(fl.ze-fl.zs)*u+fl.arc*Math.sin(Math.PI*u);
    if(fl.t>=fl.dur)land();
  }else if(st==='cel'){
    ball.z*=.9;if(scorer)spawn(WX(scorer.p.x),WZ(scorer.p.y));if(--celT<=0)kickoff(1-scorer.t);
  }
  let pr=-1,bd=9;
  for(let i=1;i<6;i++){const q=pl[1-poss][i],dd=Math.hypot(q.x-ball.x,q.y-ball.y);if(dd<bd){bd=dd;pr=i}}
  for(let t=0;t<2;t++)for(let i=0;i<6;i++){
    const p=pl[t][i];if(p.kick>0)p.kick--;
    if(st==='carry'&&hold.t===t&&hold.i===i)continue;
    if(st==='cel'){
      if(t===scorer.t){
        p.cel=true;
        if(p!==scorer.p)moveTo(p,scorer.p.x+(i-2.5)*.012,scorer.p.y+(i%3-1)*.05,SP*.9);else{p.sp*=.8;p.vx=0;p.vy=0}
      }else moveTo(p,p.x,p.y,0);
      continue;
    }
    p.cel=false;let sp=SP*.7,tx,ty;
    if(st==='fly'&&fl.rec&&fl.rec.t===t&&fl.rec.i===i){tx=fl.tx;ty=fl.ty;sp=SP*.95}
    else if(i===0){
      tx=p.hx;ty=.5+(ball.y-.5)*.25;sp=SP*.4;
      if(st==='fly'&&fl.shot&&t===1-fl.by){ty=fl.ty;sp=SP*.9}
      ty=Math.max(.41,Math.min(.59,ty));
    }else if(t!==poss&&i===pr){tx=ball.x;ty=ball.y;sp=SP*.8}
    else{const d=t?-1:1,off=(t===poss?.1:-.05)*d;tx=p.hx+(ball.x-p.hx)*.3+off;ty=p.hy+(ball.y-p.hy)*.25}
    moveTo(p,tx,ty,sp);
  }
  moveTo(ref,ball.x*.85+.075,ball.y>.5?.2:.82,SP*.55);
}
function camStep(){
  let tp,tl,k=.07;
  if(st==='cel'&&scorer){const sx=WX(scorer.p.x),sz=WZ(scorer.p.y);tp=[sx*.92,6.5*K,sz+13*K];tl=[sx,1.6,sz];k=.045}
  else{const bx=Math.max(-27,Math.min(27,WX(ball.x)));tp=[bx,14*K,27*K];tl=[bx,0,1]}
  for(let i=0;i<3;i++){cp[i]+=(tp[i]-cp[i])*k;cl[i]+=(tl[i]-cl[i])*k}
}
// ---------- render sync ----------
let lbx=0,lbz=0;
function sync(){
  const bw={x:WX(ball.x),z:WZ(ball.y)};
  const all=[];pl.forEach(tm=>tm.forEach(p=>all.push(p)));all.push(ref);
  all.forEach(p=>{
    const o=p.o,m=Math.min(1,p.sp),r=o.root;
    r.position.set(WX(p.x),0,WZ(p.y));
    let ty;
    if(p.gk)ty=p.t?-Math.PI/2:Math.PI/2;
    else if(p.sp>.15)ty=Math.atan2(p.vx*L,p.vy*WD);
    else ty=Math.atan2(bw.x-r.position.x,bw.z-r.position.z);
    let d=ty-r.rotation.y;d=Math.atan2(Math.sin(d),Math.cos(d));r.rotation.y+=d*.25;
    const sw=Math.sin(p.ph)*.95*m;
    o.legL.rotation.x=sw;o.legR.rotation.x=-sw;o.armL.rotation.x=-sw*.8;o.armR.rotation.x=sw*.8;
    let by=Math.abs(Math.sin(p.ph))*.07*m;
    if(p.cel&&st==='cel'){o.armL.rotation.x=-2.9;o.armR.rotation.x=-2.9;o.legL.rotation.x=0;o.legR.rotation.x=0;
      by=Math.abs(Math.sin(fr*.35+(p.num||0)))*.3}
    if(p.kick>0)o.legR.rotation.x=-1.3*p.kick/8;
    let lt=0;
    if(p.gk&&st==='fly'&&fl&&fl.shot&&p.t===1-fl.by){const u=fl.t/fl.dur;lt=Math.max(-1.2,Math.min(1.2,(fl.ty-p.y)*WD*.35))*u}
    o.lean+=(lt-o.lean)*.3;
    o.body.rotation.z=o.lean*(Math.sin(r.rotation.y)>=0?1:-1);
    o.body.position.y=by+Math.abs(o.lean)*.25;
  });
  const bx=WX(ball.x),bz=WZ(ball.y);
  ballMesh.position.set(bx,ball.z*PHM+.5,bz);
  ballMesh.rotation.z-=(bx-lbx)/.5;ballMesh.rotation.x+=(bz-lbz)/.5;lbx=bx;lbz=bz;
  camera.position.set(cp[0],cp[1],cp[2]);camera.lookAt(cl[0],cl[1],cl[2]);
  const ce=st==='cel'?Math.sin(fr*.6)*.006:0;crowdTexs.forEach(t=>{t.offset.y=ce});
}
// ---------- HUD ----------
const $=id=>document.getElementById(id);
let hudKey='';
function hud(){
  const k=score[0]+'-'+score[1]+'|'+min+'|'+ft;
  if(k!==hudKey){hudKey=k;$('sco').textContent=score[0]+' - '+score[1];$('clk').textContent=min>=90?'FT':min+"'";
    $('ftb').style.display=ft?'flex':'none';$('ftsc').textContent=A.c+' '+score[0]+' - '+score[1]+' '+B.c}
  $('goal').style.display=(st==='cel')?'block':'none';
  if(cmT>0){$('cm').textContent=cmTxt;$('cm').style.opacity=Math.min(1,cmT/20)}else $('cm').style.opacity=0;
}
// ---------- sizing & loop ----------
let K=1;
function fit(){
  const w=wrap.clientWidth||window.innerWidth,h=wrap.clientHeight||window.innerHeight,portrait=w/h<1;
  K=portrait?1.5:1;camera.fov=portrait?55:40;
  renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
  wrap.style.setProperty('--u',(Math.min(w,520)/100)+'px');
}
fit();addEventListener('resize',fit);
start();
let acc=0,last=performance.now(),failed=false;
function loop(now){
  if(failed)return;
  requestAnimationFrame(loop);
  try{
    acc+=Math.min(100,now-last);last=now;
    while(acc>=33){acc-=33;step();camStep();confStep();fr++;if(cmT>0)cmT--}
    sync();hud();renderer.render(scene,camera);
  }catch(e){failed=true;fallback()}
}
requestAnimationFrame(loop);
setInterval(()=>{if(!ft){if(min<90)min++;else{ft=true}}else if(++ftWait>5){start()}},700);
}catch(e){fallback()}
})();
</script>
"""

import json as _json
VIRTUAL_HTML_3D = VIRTUAL_HTML_3D_TEMPLATE.replace(
    "__FALLBACK__", _json.dumps(VIRTUAL_HTML_2D).replace("</", "<\\/"))
USE_3D = True   # set to False to use the lighter 2D match instead
VIRTUAL_HTML = VIRTUAL_HTML_3D if USE_3D else VIRTUAL_HTML_2D


# ---------- access codes ----------
def secret(name, default=""):
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _sig(key, payload):
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:10].upper()


def make_code(key, hours, now=None):
    expiry = int((now if now is not None else time.time()) + hours * 3600)
    payload = format(expiry, "X")
    return f"FB-{payload}-{_sig(key, payload)}"


def check_code(key, code, now=None):
    """Returns (valid, seconds_left_or_reason)."""
    parts = (code or "").strip().upper().replace(" ", "").split("-")
    if len(parts) != 3 or parts[0] != "FB":
        return False, "That code is not valid."
    if not hmac.compare_digest(parts[2], _sig(key, parts[1])):
        return False, "That code is not valid."
    try:
        left = int(parts[1], 16) - (now if now is not None else time.time())
    except ValueError:
        return False, "That code is not valid."
    if left <= 0:
        return False, "That code has expired. Please buy a new one."
    return True, int(left)


def time_left_text(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    d, h = divmod(h, 24)
    return (f"{d}d {h}h" if d else f"{h}h {m}m")


# ---------- live results from football-data.org (optional, free key) ----------
FD_ORG = {"PL": "E0", "ELC": "E1", "PD": "SP1", "SA": "I1", "BL1": "D1",
          "FL1": "F1", "DED": "N1", "PPL": "P1"}      # football-data.org code -> our league code
FD_ALIASES = {   # their spelling -> spelling used in our data
    "manchester united": "Man United", "manchester city": "Man City",
    "nottingham forest": "Nott'm Forest", "wolverhampton wanderers": "Wolves",
    "wolverhampton": "Wolves", "tottenham hotspur": "Tottenham", "newcastle united": "Newcastle",
    "brighton hove albion": "Brighton", "brighton": "Brighton", "west ham united": "West Ham",
    "leeds united": "Leeds", "leicester city": "Leicester", "ipswich town": "Ipswich",
    "luton town": "Luton", "sheffield united": "Sheffield United", "norwich city": "Norwich",
    "cardiff city": "Cardiff", "swansea city": "Swansea", "stoke city": "Stoke",
    "hull city": "Hull", "coventry city": "Coventry", "birmingham city": "Birmingham",
    "queens park rangers": "QPR", "west bromwich albion": "West Brom",
    "sheffield wednesday": "Sheffield Weds", "preston north end": "Preston",
    "oxford united": "Oxford", "derby county": "Derby", "bristol city": "Bristol City",
    "atletico madrid": "Ath Madrid", "club atletico de madrid": "Ath Madrid",
    "athletic club": "Ath Bilbao", "real sociedad": "Sociedad", "real betis": "Betis",
    "rayo vallecano": "Vallecano", "celta vigo": "Celta", "rc celta": "Celta",
    "deportivo alaves": "Alaves", "rcd espanyol": "Espanol", "espanyol": "Espanol",
    "real valladolid": "Valladolid", "ud las palmas": "Las Palmas", "cd leganes": "Leganes",
    "internazionale": "Inter", "internazionale milano": "Inter", "fc internazionale milano": "Inter",
    "ac milan": "Milan", "as roma": "Roma", "ssc napoli": "Napoli", "ss lazio": "Lazio",
    "hellas verona": "Verona", "bayern munchen": "Bayern Munich", "fc bayern munchen": "Bayern Munich",
    "borussia monchengladbach": "M'gladbach", "borussia dortmund": "Dortmund",
    "bayer 04 leverkusen": "Leverkusen", "bayer leverkusen": "Leverkusen",
    "eintracht frankfurt": "Ein Frankfurt", "rb leipzig": "RB Leipzig", "vfb stuttgart": "Stuttgart",
    "1 fc union berlin": "Union Berlin", "fc augsburg": "Augsburg", "sc freiburg": "Freiburg",
    "tsg 1899 hoffenheim": "Hoffenheim", "vfl wolfsburg": "Wolfsburg", "vfl bochum 1848": "Bochum",
    "werder bremen": "Werder Bremen", "1 fsv mainz 05": "Mainz", "fc st pauli 1910": "St Pauli",
    "1 fc heidenheim 1846": "Heidenheim", "holstein kiel": "Holstein Kiel",
    "paris saint germain": "Paris SG", "olympique de marseille": "Marseille",
    "olympique lyonnais": "Lyon", "as monaco": "Monaco", "losc lille": "Lille",
    "stade rennais": "Rennes", "stade brestois 29": "Brest", "ogc nice": "Nice",
    "rc strasbourg alsace": "Strasbourg", "stade de reims": "Reims", "as saint etienne": "St Etienne",
    "psv": "PSV Eindhoven", "sc heerenveen": "Heerenveen", "fc utrecht": "Utrecht",
    "az": "AZ Alkmaar", "go ahead eagles": "Go Ahead Eagles", "fc twente": "Twente",
    "fc groningen": "Groningen", "sparta rotterdam": "Sparta Rotterdam", "nec": "Nijmegen",
    "sporting clube de portugal": "Sporting", "sporting cp": "Sporting", "sl benfica": "Benfica",
    "fc porto": "Porto", "sporting clube de braga": "Sp Braga", "sc braga": "Sp Braga",
    "vitoria sc": "Guimaraes", "vitoria guimaraes": "Guimaraes",
}
_FD_STOP = {"fc", "afc", "cf", "ac", "as", "ssc", "sc", "rc", "rcd", "ud", "cd", "ca", "us", "fk",
            "sv", "vfb", "vfl", "tsg", "fsv", "1", "04", "05", "96", "1899", "1846", "de", "calcio"}


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def _toks(s):
    return {t for t in _fold(s).split() if t not in _FD_STOP}


def match_team(api_names, csv_names):
    """Find our spelling of a team from football-data.org's name(s), or None if unsure."""
    for n in api_names:
        f = _fold(n)
        short = " ".join(w for w in f.split() if w not in ("fc", "afc", "cf"))
        for key in (f, short):
            a = FD_ALIASES.get(key)
            if a and a in csv_names:
                return a
    best, score, ties = None, 0, 0
    for n in api_names:
        at = _toks(n)
        for c in csv_names:
            ct = _toks(c)
            if not at or not ct or not (ct <= at or at <= ct):
                continue
            sc = len(ct & at)
            if sc > score:
                best, score, ties = c, sc, 1
            elif sc == score and c != best:
                ties += 1
    return best if score and ties == 1 else None


def merge_live_results(cache):
    """Adds finished matches of the last 9 days from football-data.org to the league
    data. Needs FOOTBALL_DATA_ORG_KEY in Secrets. Never raises: on any problem the
    normal data is used unchanged. Returns the number of matches added."""
    token = secret("FOOTBALL_DATA_ORG_KEY")
    if not token:
        return 0
    try:
        today = datetime.now(timezone.utc).date()
        q = urllib.parse.urlencode({"dateFrom": (today - timedelta(days=9)).isoformat(),
                                    "dateTo": (today + timedelta(days=1)).isoformat(),
                                    "status": "FINISHED"})
        req = urllib.request.Request("https://api.football-data.org/v4/matches?" + q,
                                     headers={"X-Auth-Token": token})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
        added = 0
        names = {}
        for m in data.get("matches") or []:
            div = FD_ORG.get((m.get("competition") or {}).get("code"))
            ft = ((m.get("score") or {}).get("fullTime")) or {}
            if not div or ft.get("home") is None or ft.get("away") is None:
                continue
            rows = cache.get(div)
            if not rows:
                continue
            if div not in names:
                names[div] = {r["home"] for r in rows} | {r["away"] for r in rows}
            h, a = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            home = match_team([h.get("name"), h.get("shortName")], names[div])
            away = match_team([a.get("name"), a.get("shortName")], names[div])
            if not home or not away or home == away:
                continue
            d = datetime.strptime(m["utcDate"][:10], "%Y-%m-%d")
            if any(r["home"] == home and r["away"] == away and abs((r["date"] - d).days) <= 2
                   for r in rows):
                continue
            row = {"date": d, "home": home, "away": away,
                   "hg": int(ft["home"]), "ag": int(ft["away"])}
            for k in p.STAT_COLS:
                row[k] = None
            rows.append(row)
            added += 1
        return added
    except Exception:
        return 0


# ---------- key players and injuries ----------
@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _scorers():
    """Top scorers per team from football-data.org (free key). Raises if nothing came
    back, so a failure is not cached."""
    token = secret("FOOTBALL_DATA_ORG_KEY")
    out = {}
    if token:
        cache = league_data()
        for code, div in FD_ORG.items():
            rows = cache.get(div)
            if not rows:
                continue
            try:
                names = {r["home"] for r in rows} | {r["away"] for r in rows}
                req = urllib.request.Request(
                    f"https://api.football-data.org/v4/competitions/{code}/scorers?limit=80",
                    headers={"X-Auth-Token": token})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8"))
                for s in data.get("scorers") or []:
                    t = s.get("team") or {}
                    team = match_team([t.get("name"), t.get("shortName")], names)
                    pl = (s.get("player") or {}).get("name")
                    if team and pl and s.get("goals") is not None:
                        out.setdefault(team, []).append(
                            (pl, int(s.get("goals") or 0), int(s.get("assists") or 0)))
            except Exception:
                continue
    if not out:
        raise RuntimeError("no scorers")
    return out


def key_players(team):
    try:
        return sorted(_scorers().get(team, []), key=lambda x: -x[1])[:3]
    except Exception:
        return []


def injuries_for(team):
    """Reads injuries.txt (beside this file). One line per team:  Arsenal: Saka (knee), Gabriel"""
    try:
        path = Path(__file__).parent / "injuries.txt"
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    me = _fold(team)
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, players = line.split(":", 1)
        n = _fold(name)
        if n and (n == me or (len(n) >= 4 and (n in me or me in n))):
            found += [x.strip() for x in players.split(",") if x.strip()]
    return found


def players_block(team):
    inj = injuries_for(team)
    inj_fold = " ".join(_fold(x) for x in inj)
    kp = key_players(team)
    st.markdown(f"**{team}**")
    if kp:
        for name, g, a in kp:
            last = (_fold(name).split() or [""])[-1]
            out = " 🚑 *injured*" if last and last in inj_fold else ""
            st.markdown(f"⭐ {name} · {g} goals, {a} assists this season{out}")
    else:
        st.caption("Key players not available for this league.")
    if inj:
        st.markdown("🩹 **Injured / doubtful:** " + ", ".join(inj))
    else:
        st.caption("No injuries listed.")


# ---------- prediction ----------
@st.cache_resource(ttl=6 * 3600, show_spinner=False)
def league_data():
    """All leagues downloaded once and shared by every visitor (6 hours)."""
    cache = {}
    p.load_all(cache)
    if not any(cache.values()):
        # Raising means Streamlit does NOT cache this failure.
        raise RuntimeError("Could not download match data right now. Please try again.")
    merge_live_results(cache)
    return cache


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def get_picks(days):
    """Returns (result, error). Cached for 3 hours."""
    try:
        return pk.compute_picks(league_data(), days), None
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Something went wrong: {e}"


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def get_results():
    """Returns (result, error). Back-test of the last 7 days. Cached for 3 hours."""
    try:
        return pk.compute_results(league_data(), 7), None
    except Exception as e:
        return None, f"Something went wrong: {e}"


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def get_all_matches():
    """Every upcoming fixture (next 7 days) in every league we have data for, with the
    model's prediction. Returns (result, error). Cached for 3 hours."""
    try:
        fixtures = pk.load_fixtures()
        cache = league_data()
        today = datetime.now(timezone.utc).date()
        end = today + timedelta(days=7)
        per_div, out, skipped = {}, [], 0
        for f in fixtures:
            if not (today <= f["date"] < end):
                continue
            div = f["div"]
            if div not in per_div:
                rows = cache.get(div) or []
                names = {r["home"] for r in rows} | {r["away"] for r in rows}
                ratings, avg = p.ratings_from(rows) if rows else ({}, p.DEFAULT_AVG_GOALS)
                per_div[div] = (rows, names, ratings, avg, p.shot_ratings_from(rows))
            rows, names, ratings, avg, shot = per_div[div]
            if not rows:
                skipped += 1
                continue

            def resolve(q):
                if q in names:
                    return q
                hits = p.find_team_names(q, rows)
                return hits[0] if hits else None

            home, away = resolve(f["home"]), resolve(f["away"])
            if not home or not away or home == away:
                skipped += 1
                continue
            hm, am = p.last_matches(home, rows), p.last_matches(away, rows)
            if len(hm) < 3 or len(am) < 3:
                skipped += 1
                continue
            pr = p.predict(p.summarise(hm, ratings, True, shot),
                           p.summarise(am, ratings, False, shot), avg)
            total = pr["xg_home"] + pr["xg_away"]
            out.append({"date": f["date"], "time": f["time"], "div": div,
                        "league": p.LEAGUES.get(div, div), "home": home, "away": away,
                        "pr": pr, "over15": 1 - math.exp(-total) * (1 + total)})
        out.sort(key=lambda m: (m["date"], m["time"] or "99:99", m["league"]))
        return {"matches": out, "skipped": skipped}, None
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Something went wrong: {e}"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def compute(home_q, away_q):
    """Returns (data, error). Cached for 6 hours per team pair."""
    try:
        cache = league_data()
        with contextlib.redirect_stdout(io.StringIO()):
            hn, hrows = p.locate(home_q, cache)
            an, arows = p.locate(away_q, cache)
        pool = hrows if hrows is arows else hrows + arows
        ratings, avg = p.ratings_from(pool)
        hm, am = p.last_matches(hn, pool), p.last_matches(an, pool)
        if len(hm) < 3 or len(am) < 3:
            return None, "Not enough recent matches found for one of the teams."
        shot = p.shot_ratings_from(pool)
        hs, as_ = p.summarise(hm, ratings, True, shot), p.summarise(am, ratings, False, shot)
        return {"home": hn, "away": an, "hm": hm, "am": am,
                "hs": hs, "as": as_, "pred": p.predict(hs, as_, avg)}, None
    except (SystemExit, RuntimeError) as e:
        return None, str(e)
    except Exception as e:
        return None, f"Something went wrong: {e}"


def form_badges(form):
    return "".join({"W": "🟩", "D": "🟨", "L": "🟥"}[c] for c in form)


def team_card(name, matches, s, playing_home):
    st.markdown(f"**{name}**")
    st.markdown(f"<div class='form'>{form_badges(s['form'])}</div>",
                unsafe_allow_html=True)
    st.caption(f"W{s['w']} D{s['d']} L{s['l']} · scores {s['gf']:.2f} / "
               f"concedes {s['ga']:.2f} per game · {s['clean']} clean sheets")
    rows = ["| Date | | Opponent | Score |", "|---|---|---|---|"]
    for m in matches:
        v = "H" if m["home"] else "A"
        mark = "**" if m["home"] == playing_home else ""
        rows.append(f"| {m['date'][5:]} | {v} | {mark}{m['opp']}{mark} | "
                    f"{m['gf']}-{m['ga']} |")
    st.markdown("\n".join(rows))
    where = "home" if playing_home else "away"
    if s["venue_n"]:
        st.caption(f"Bold = {where} games (counted double). At {where}: "
                   f"{s['venue_gf']:.2f} scored / {s['venue_ga']:.2f} conceded.")


STAT_ROWS = [  # (label, key, kind)
    ("Goals scored per match", "goals_for", "2"),
    ("Goals conceded per match", "goals_against", "2"),
    ("Average goals (both teams, per match)", "avg_goals", "2"),
    ("Failed to score (of last 6)", "failed_to_score", "int"),
    ("Shots taken per match", "shots", "1"),
    ("Shots faced per match", "shots_against", "1"),
    ("Avg. shots on target", "sot", "1"),
    ("Avg. shots on target against", "sot_against", "1"),
    ("Avg. shots off target", "off_target", "1"),
    ("Shots off/on-target ratio", "off_on_ratio", "2"),
    ("Avg. shots per goal", "shots_per_goal", "1"),
    ("Shooting conversion rate", "conversion", "pct"),
    ("Scoring efficiency (goals per shot on target)", "scoring_eff", "pct"),
    ("Conceding efficiency (goals per shot on target faced)", "conceding_eff", "pct"),
    ("Avg. corners", "corners", "1"),
    ("Avg. corners against", "corners_against", "1"),
    ("Avg. fouls", "fouls", "1"),
    ("Avg. yellow cards", "yellows", "2"),
    ("Avg. red cards", "reds", "2"),
]


def _fmt_stat(v, kind):
    if v is None:
        return "n/a"
    if kind == "int":
        return str(int(v))
    if kind == "pct":
        return f"{v:.0%}"
    return f"{v:.{kind}f}"


def stats_table(data):
    hs, as_ = data["hs"]["stats"], data["as"]["stats"]
    rows = [f"| Last 6 matches | {data['home']} | {data['away']} |", "|---|---|---|"]
    for label, key, kind in STAT_ROWS:
        rows.append(f"| {label} | {_fmt_stat(hs.get(key), kind)} | {_fmt_stat(as_.get(key), kind)} |")
    st.markdown("\n".join(rows))
    short = [n for n in (hs["n_shots"], as_["n_shots"]) if n < hs["n"]]
    if short:
        st.caption("Shot figures use only the matches where the data has them "
                   f"({data['home']}: {hs['n_shots']} of {hs['n']}, "
                   f"{data['away']}: {as_['n_shots']} of {as_['n']}). 'n/a' = not in the data.")
    st.caption("Not available in the free data: possession, attacks, dangerous attacks, "
               "shots inside/outside the box, goal kicks, penalties, offsides.")


def show_result(data):
    pr = data["pred"]
    (i, j), prob = pr["top"][0]
    st.divider()
    st.markdown(f"<div class='teams'>{data['home']} vs {data['away']}</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div class='big-score'>{i} - {j}</div>", unsafe_allow_html=True)
    alt = ", ".join(f"{a}-{b} ({q:.0%})" for (a, b), q in pr["top"][1:])
    st.markdown(f"<div class='sub'>Most likely score ({prob:.0%}) · "
                f"also: {alt}<br>Expected goals "
                f"{pr['xg_home']:.2f} - {pr['xg_away']:.2f}</div>",
                unsafe_allow_html=True)
    for label, val in ((f"{data['home']} win", pr["home"]), ("Draw", pr["draw"]),
                       (f"{data['away']} win", pr["away"])):
        st.progress(min(max(val, 0.0), 1.0), text=f"{label}: {val:.0%}")
    total = pr["xg_home"] + pr["xg_away"]
    over15 = 1 - math.exp(-total) * (1 + total)
    c1, c2, c3 = st.columns(3)
    c1.metric("Over 1.5 goals", f"{over15:.0%}")
    c2.metric("Over 2.5 goals", f"{pr['over25']:.0%}")
    c3.metric("Both teams score", f"{pr['btts']:.0%}")
    with st.expander("📊 Team stats (last 6 matches)", expanded=True):
        stats_table(data)
    with st.expander("⭐ Key players & 🩹 injuries", expanded=True):
        players_block(data["home"])
        players_block(data["away"])
        st.caption("Key players = the team's top scorers this season. Injuries are "
                   "updated by hand, so check team news before kickoff. The "
                   "prediction itself does not change for injuries.")
    with st.expander(f"{data['home']} - last 6 matches", expanded=True):
        team_card(data["home"], data["hm"], data["hs"], True)
    with st.expander(f"{data['away']} - last 6 matches", expanded=True):
        team_card(data["away"], data["am"], data["as"], False)
    st.caption("Statistical estimate from recent form only. Not a guarantee "
               "and not betting advice.")


def show_locked(data, key):
    """Only team names are shown. No prediction data is sent to the viewer."""
    st.divider()
    st.markdown(f"<div class='teams'>{data['home']} vs {data['away']}</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='big-score'>? - ?</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub'>🔒 Prediction locked. Pay to unlock it.</div>",
                unsafe_allow_html=True)
    payment_box(key, "predict")


def predictor_ui(has_access, key):
    st.caption("Based on each team's last 6 matches. Try: Arsenal, Man United, "
               "Man City, Ath Madrid, Inter, Bayern (partial names work).")
    home = st.text_input("Home team", placeholder="Arsenal")
    away = st.text_input("Away team", placeholder="Chelsea")
    if st.button("Predict", type="primary", use_container_width=True):
        if not home.strip() or not away.strip():
            st.session_state.pop("pending", None)
            st.warning("Type both team names.")
        else:
            st.session_state["pending"] = (home.strip(), away.strip())
    pending = st.session_state.get("pending")
    if not pending:
        return
    with st.spinner("Fetching latest results (first time takes ~20s)..."):
        data, err = compute(*pending)
    if err:
        st.error(err)
    elif has_access:
        show_result(data)
    else:
        show_locked(data, key)


# ---------- Uganda time ----------
UK_TZ, UG_TZ = ZoneInfo("Europe/London"), ZoneInfo("Africa/Kampala")


def ug_when(d, t):
    """Fixture date + UK clock time text -> (date, 'HH:MM') in Uganda time."""
    try:
        hh, mm = (int(x) for x in (t or "").split(":")[:2])
        dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=UK_TZ).astimezone(UG_TZ)
        return dt.date(), dt.strftime("%H:%M")
    except Exception:
        return d, (t or "")


def with_ug(ms):
    """Adds 'ugd' (Uganda date) and 'ugt' (Uganda time) to every match."""
    for m in ms:
        m["ugd"], m["ugt"] = ug_when(m["date"], m["time"])
    return ms


# ---------- manual matches (added by the owner) ----------
MANUAL_FILE = Path(__file__).parent / "manual_matches.json"


def load_manual():
    try:
        data = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_manual(items):
    try:
        MANUAL_FILE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def markets_from_pred(pr):
    """Turn a match prediction into pick markets: all that reach 70%, else the best two."""
    total = pr["xg_home"] + pr["xg_away"]
    o15 = 1 - math.exp(-total) * (1 + total)
    cand = [("Home win", pr["home"]), ("Away win", pr["away"]),
            ("Over 1.5 goals", o15), ("Over 2.5 goals", pr["over25"]),
            ("Under 2.5 goals", 1 - pr["over25"]),
            ("Both teams score: Yes", pr["btts"]), ("Both teams score: No", 1 - pr["btts"]),
            ("Home or draw", pr["home"] + pr["draw"]), ("Away or draw", pr["away"] + pr["draw"])]
    cand.sort(key=lambda x: -x[1])
    return [c for c in cand if c[1] >= 0.70][:4] or cand[:2]


def manual_picks():
    """Owner-added matches from today on, shaped like the normal Top picks entries."""
    out = []
    today = datetime.now(UG_TZ).date()
    for it in load_manual():
        try:
            d = datetime.strptime(it["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d < today:
            continue
        data, err = compute(it["home"], it["away"])
        if err or not data:
            continue
        out.append({"home": data["home"], "away": data["away"],
                    "league": it.get("league") or "Featured match",
                    "ugd": d, "ugt": it.get("time") or "",
                    "picks": markets_from_pred(data["pred"])})
    return out


def manual_admin():
    st.markdown("**📝 Add a match manually**")
    st.caption("Use this when Top picks has no games. Type the two teams the same way "
               "as in the Predict a match tab. The model works out the picks. "
               "Time is Uganda time.")
    home = st.text_input("Home team", key="mm_home")
    away = st.text_input("Away team", key="mm_away")
    league = st.text_input("Competition (optional)", key="mm_league",
                           placeholder="Champions League")
    c1, c2 = st.columns(2)
    d = c1.date_input("Date", value=datetime.now(UG_TZ).date(), key="mm_date")
    t = c2.time_input("Kick-off", value=dtime(20, 45), key="mm_time")
    if st.button("Add match", key="mm_add", use_container_width=True):
        if not home.strip() or not away.strip():
            st.warning("Type both team names.")
        else:
            data, err = compute(home.strip(), away.strip())
            if err or not data:
                st.error(err or "Could not find those teams.")
            else:
                items = load_manual()
                entry = {"id": hashlib.md5(f"{data['home']}{data['away']}{d}{t}".encode()).hexdigest()[:8],
                         "home": data["home"], "away": data["away"],
                         "league": league.strip(), "date": d.isoformat(),
                         "time": t.strftime("%H:%M")}
                if any(x.get("id") == entry["id"] for x in items):
                    st.info("That match is already added.")
                else:
                    items.append(entry)
                    if save_manual(items):
                        st.success(f"Added {data['home']} vs {data['away']}. "
                                   "It now shows in Top picks.")
                    else:
                        st.error("Could not save the match on the server.")
    items = load_manual()
    if items:
        st.markdown("**Matches you added**")
        for x in sorted(items, key=lambda x: (x.get("date", ""), x.get("time", ""))):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"{x['home']} vs {x['away']}  \n"
                        f"<small>{x.get('date', '')} {x.get('time', '')}</small>",
                        unsafe_allow_html=True)
            if c2.button("🗑", key=f"mm_del_{x['id']}"):
                save_manual([y for y in items if y.get("id") != x["id"]])
                st.rerun()
        st.caption("Past matches are hidden automatically. Saved on the server, so they "
                   "may be cleared if the app is rebooted or redeployed.")


# ---------- paywall screens ----------
FREE_PICKS = 1   # how many matches free visitors see in full on the Top picks tab


def picks_tab(has_access, key):
    with st.spinner("Loading today's picks (first time can take ~30 seconds)..."):
        res, err = get_picks(1)
        look = 1
        manual = manual_picks()
        if not err and not res["matches"] and not manual:
            # Nothing in our leagues today (e.g. a Champions League night):
            # show the next days that do have matches instead of an empty page.
            for d in (3, 7):
                r2, e2 = get_picks(d)
                if not e2 and r2["matches"]:
                    res, look = r2, d
                    break
    if err:
        st.error(err)
        return
    ms = sorted(with_ug([dict(m) for m in res["matches"]]) + manual,
                key=lambda m: (m["ugd"], -m["picks"][0][1]))
    when = "Today" if look == 1 else f"Next {look} days"
    st.caption(f"{when} · {len(ms)} high-confidence pick"
               f"{'' if len(ms) == 1 else 's'} from {res['analysed'] + len(manual)} matches analysed. "
               "Times are Uganda time (EAT).")
    if look > 1:
        st.info("No matches in our leagues today, so here are the next days' picks. "
                "Our data covers domestic leagues, not Champions League or Europa League.")
    # Free visitors get the FREE_PICKS strongest matches in full; the rest stay locked.
    best = sorted(range(len(ms)), key=lambda i: -ms[i]["picks"][0][1])
    free_ids = set() if has_access else set(best[:FREE_PICKS])
    if not has_access:
        locked_n = len(ms) - len(free_ids)
        if locked_n > 0:
            st.markdown(f"**🎁 Here are {len(free_ids)} free picks. "
                        f"🔒 {locked_n} more are locked. Unlock to see them, "
                        "the percentages and the full analysis.**")
        payment_box(key, "picks")
    if not ms:
        st.info("No high-confidence picks today. Check again later.")
    else:
        st.markdown("### 📋 All top picks")
    day = None
    for i, m in enumerate(ms):
        if m["ugd"] != day:
            day = m["ugd"]
            st.markdown(f"<div class='day'>{day.strftime('%A, %d %B')}</div>",
                        unsafe_allow_html=True)
        if has_access or i in free_ids:
            free_tag = "" if has_access else "<span class='pill hot'>🎁 FREE</span>"
            pills = free_tag + "".join(
                f"<span class='pill{' hot' if pr >= 0.75 else ''}'>{html.escape(mk)} · {pr:.0%}</span>"
                for mk, pr in m["picks"])
        else:
            n = len(m["picks"])
            pills = f"<span class='pill lock'>🔒 {n} pick{'' if n == 1 else 's'} locked</span>"
        st.markdown(
            f"<div class='pick'><div class='meta'>{html.escape(m['league'])} · "
            f"{html.escape(m['ugt'])}</div><div class='vs'>{html.escape(m['home'])} vs "
            f"{html.escape(m['away'])}</div>{pills}</div>", unsafe_allow_html=True)
        if has_access or i in free_ids:
            pid = f"{m['home']}|{m['away']}"
            opened = st.session_state.get("open_pick") == pid
            if st.button("✖ Close analysis" if opened else "📈 See analysis",
                         key=f"an_{pid}", use_container_width=True):
                st.session_state["open_pick"] = None if opened else pid
                st.rerun()
            if opened:
                with st.spinner("Loading analysis..."):
                    data, aerr = compute(m["home"], m["away"])
                if aerr:
                    st.error(aerr)
                else:
                    show_result(data)
    st.caption("Model estimates from recent form. Not guarantees and not betting advice.")


def all_tab(has_access, key):
    """Every league: all upcoming fixtures. Full predictions for paid clients only."""
    with st.spinner("Loading all leagues (first time can take ~30 seconds)..."):
        res, err = get_all_matches()
    if err:
        st.error(err)
        return
    ms = res["matches"]
    if not ms:
        st.info("No upcoming fixtures found in the data right now. Check again later.")
        return
    ms = sorted(with_ug([dict(m) for m in ms]), key=lambda m: (m["ugd"], m["ugt"] or "99:99", m["league"]))
    today = datetime.now(UG_TZ).date()
    span = st.radio("Show matches", ["Today", "Tomorrow", "Next 3 days", "Next 7 days"],
                    horizontal=True, key="all_span")
    first, last = {"Today": (0, 1), "Tomorrow": (1, 2), "Next 3 days": (0, 3),
                   "Next 7 days": (0, 7)}[span]
    ms = [m for m in ms if today + timedelta(days=first) <= m["ugd"] < today + timedelta(days=last)]
    leagues = sorted({m["league"] for m in ms})
    pick = st.selectbox("League", ["All leagues"] + leagues, key="all_league")
    if pick != "All leagues":
        ms = [m for m in ms if m["league"] == pick]
    st.caption(f"{len(ms)} match{'' if len(ms) == 1 else 'es'} · "
               f"{len({m['league'] for m in ms})} league(s). Times are Uganda time (EAT).")
    if not has_access:
        st.markdown("**🔒 Predictions for every league are for paying clients. "
                    "Unlock to see the predicted score, win chances, goals and "
                    "full analysis for each match below.**")
        payment_box(key, "all")
    if not ms:
        st.info("No matches for this choice.")
        return
    day = None
    for m in ms:
        if m["ugd"] != day:
            day = m["ugd"]
            st.markdown(f"<div class='day'>{day.strftime('%A, %d %B')}</div>",
                        unsafe_allow_html=True)
        head = (f"<div class='meta'>{html.escape(m['league'])} · {html.escape(m['ugt'])}</div>"
                f"<div class='vs'>{html.escape(m['home'])} vs {html.escape(m['away'])}</div>")
        if has_access:
            pr = m["pr"]
            (i, j), _ = pr["top"][0]
            pills = (f"<span class='pill hot'>Score {i}-{j}</span>"
                     f"<span class='pill'>1 {pr['home']:.0%}</span>"
                     f"<span class='pill'>X {pr['draw']:.0%}</span>"
                     f"<span class='pill'>2 {pr['away']:.0%}</span>"
                     f"<span class='pill'>xG {pr['xg_home']:.1f}-{pr['xg_away']:.1f}</span>"
                     f"<span class='pill'>Over 1.5 {m['over15']:.0%}</span>"
                     f"<span class='pill'>Over 2.5 {pr['over25']:.0%}</span>"
                     f"<span class='pill'>BTTS {pr['btts']:.0%}</span>")
        else:
            pills = "<span class='pill lock'>🔒 Prediction locked</span>"
        st.markdown(f"<div class='pick'>{head}{pills}</div>", unsafe_allow_html=True)
        if has_access:
            pid = f"{m['home']}|{m['away']}"
            opened = st.session_state.get("open_all") == pid
            if st.button("✖ Close analysis" if opened else "📈 See analysis",
                         key=f"all_{pid}", use_container_width=True):
                st.session_state["open_all"] = None if opened else pid
                st.rerun()
            if opened:
                with st.spinner("Loading analysis..."):
                    data, aerr = compute(m["home"], m["away"])
                if aerr:
                    st.error(aerr)
                else:
                    show_result(data)
    if res["skipped"]:
        st.caption(f"{res['skipped']} fixture(s) left out because there is not enough "
                   "recent data for one of the teams.")
    st.caption("1 = home win, X = draw, 2 = away win. Model estimates from recent form. "
               "Not guarantees and not betting advice.")


def results_tab():
    """Past results. Visible to everyone: old picks have no betting value."""
    with st.spinner("Loading results (first time can take ~30 seconds)..."):
        res, err = get_results()
    if err:
        st.error(f"Results could not load: {err}")
        return
    days = [d for d in res["days"] if d["total"]]
    if not days:
        st.info("No finished picks to show yet. Check again later.")
        return
    st.caption("Tap a date to see every pick for that day, marked ✅ hit or ❌ miss. "
               "Back-tested: the same model and rules re-run on the data that was "
               "available before each match. Wins and losses are all shown.")
    try:
        latest = max(r["date"].date() for rows in league_data().values() for r in rows)
        if latest < datetime.now(timezone.utc).date() - timedelta(days=1):
            st.info(f"📅 Our results data is up to {latest.strftime('%a %d %b')}. "
                    "Newer days appear here automatically when the data provider "
                    "updates it, usually within a few days.")
    except Exception:
        pass
    labels = {d["date"].strftime("%a %d %b"): d for d in days}
    choice = st.radio("Choose a date", list(labels), horizontal=True)
    d = labels[choice]
    st.markdown(f"**{d['hits']} of {d['total']} picks hit ({d['hits'] / d['total']:.0%})**")
    for m in d["matches"]:
        pills = "".join(
            f"<span class='pill {'hot' if x['hit'] else 'miss'}'>"
            f"{'✅' if x['hit'] else '❌'} {html.escape(x['market'])} · {x['prob']:.0%}</span>"
            for x in m["picks"])
        st.markdown(
            f"<div class='pick'><div class='meta'>{html.escape(m['league'])} · "
            f"Final score {html.escape(m['score'])}</div><div class='vs'>"
            f"{html.escape(m['home'])} vs {html.escape(m['away'])}</div>{pills}</div>",
            unsafe_allow_html=True)


def payment_box(key, where):
    price = secret("PRICE_TEXT", "Ask the owner for the price")
    how = secret("PAY_INSTRUCTIONS", "Contact the owner to pay.")
    st.markdown(f"**Price:** {price}")
    st.markdown(f"**How to pay:** {how}")
    wa = secret("WHATSAPP_NUMBER")
    if wa:
        msg = quote("Hello, I have paid for Score Predictor access. Please send my code.")
        st.markdown(f"After paying, [send us the payment message on WhatsApp]"
                    f"(https://wa.me/{wa}?text={msg}) and we'll send your access code.")
    else:
        st.markdown("After paying, send the payment message to the owner to get your code.")
    code = st.text_input("Have a code? Enter it here", placeholder="FB-XXXXXXXX-XXXXXXXXXX",
                         key=f"code_{where}")
    if st.button("Unlock", use_container_width=True, key=f"unlock_{where}"):
        ok, info = check_code(key, code)
        if ok:
            st.session_state["code"] = code.strip()
            st.query_params["code"] = code.strip()
            st.rerun()
        else:
            st.error(info)


def owner_panel(key, admin_pw):
    with st.expander("Owner login"):
        if not st.session_state.get("admin_ok"):
            pw = st.text_input("Owner password", type="password", key="pw")
            if st.button("Log in"):
                if hmac.compare_digest(pw, admin_pw):
                    st.session_state["admin_ok"] = True
                    st.rerun()
                else:
                    st.error("Wrong password.")
            return
        st.success("Logged in as owner.")
        label = st.selectbox("Pass length", list(PASSES))
        if st.button("Generate access code"):
            code = make_code(key, PASSES[label])
            st.code(code, language=None)
            st.text_area("Message to send the customer",
                         f"Thank you! Your Score Predictor access code is:\n{code}\n"
                         f"Valid for {label.split(' (')[0].lower()} from now. "
                         "Enter it on the site and tap Unlock.")
        st.divider()
        manual_admin()
        st.divider()
        if st.button("Log out"):
            st.session_state["admin_ok"] = False
            st.rerun()


# ---------- main ----------
key, admin_pw = secret("CODE_SECRET"), secret("ADMIN_PASSWORD")
if not key or not admin_pw:
    st.error("This site is not set up yet. The owner must add CODE_SECRET and "
             "ADMIN_PASSWORD in the app's Secrets settings.")
    st.stop()

has_access = bool(st.session_state.get("admin_ok"))
notice = None
if not has_access:
    code = st.session_state.get("code") or st.query_params.get("code", "")
    ok, info = check_code(key, code)
    if ok:
        has_access = True
        notice = ("caption", f"✅ Access active - {time_left_text(info)} left")
    elif code:
        notice = ("warning", info)
        st.session_state.pop("code", None)

# Virtual match plays full screen behind the whole page (see CSS at the top)
components.html(VIRTUAL_HTML, height=1)
st.markdown("<div class='hero'><div class='hero-t'>⚽ Score Predictor</div>"
            "<div class='hero-s'>🔴 Live virtual match</div></div>", unsafe_allow_html=True)

try:
    sheet = st.container(key="sheet")
except TypeError:            # older Streamlit without container keys
    sheet = st.container()
with sheet:
    if notice:
        getattr(st, notice[0])(notice[1])
    tab_picks, tab_all, tab_results, tab_pred = st.tabs(
        ["🔥 Top picks", "🌍 All leagues", "📊 Results", "🔍 Predict a match"])
    with tab_picks:
        picks_tab(has_access, key)
    with tab_all:
        all_tab(has_access, key)
    with tab_results:
        results_tab()
    with tab_pred:
        predictor_ui(has_access, key)
    owner_panel(key, admin_pw)
