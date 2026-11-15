import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js';

const mount = document.getElementById('fbm3d-canvas');
const errorBox = document.getElementById('fbm3d-error');
const scoreEl = document.getElementById('fbm3d-score-value');
const clockEl = document.getElementById('fbm3d-clock');
const statusEl = document.getElementById('fbm3d-status');
const pauseBtn = document.getElementById('fbm3d-pause');
const restartBtn = document.getElementById('fbm3d-restart');

try {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x8fb1c0);
  scene.fog = new THREE.Fog(0x8fb1c0, 105, 220);
  const camera = new THREE.PerspectiveCamera(54, 1, .1, 420);
  const renderer = new THREE.WebGLRenderer({ antialias:true, powerPreference:'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.6));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping;
  mount.appendChild(renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xe9f5ff,0x31523a,2.1));
  const sun = new THREE.DirectionalLight(0xfff0d2,2.5); sun.position.set(-30,65,25); sun.castShadow=true; sun.shadow.mapSize.set(1536,1536); scene.add(sun);

  const ground = new THREE.Mesh(new THREE.PlaneGeometry(290,220),new THREE.MeshStandardMaterial({color:0x183b2b,roughness:1})); ground.rotation.x=-Math.PI/2; ground.position.y=-.2; ground.receiveShadow=true; scene.add(ground);
  const field = new THREE.Mesh(new THREE.PlaneGeometry(180,112),new THREE.MeshStandardMaterial({color:0x267b43,roughness:.95})); field.rotation.x=-Math.PI/2; field.receiveShadow=true; scene.add(field);
  for(let i=0;i<10;i++){const m=new THREE.Mesh(new THREE.PlaneGeometry(18,112),new THREE.MeshStandardMaterial({color:i%2?0x2b8548:0x24753f}));m.rotation.x=-Math.PI/2;m.position.set(-81+i*18,.012,0);scene.add(m);}
  const white=new THREE.MeshBasicMaterial({color:0xf4f5e9});
  function line(x1,z1,x2,z2,w=.15){const dx=x2-x1,dz=z2-z1,len=Math.hypot(dx,dz);const o=new THREE.Mesh(new THREE.BoxGeometry(len,w,.035),white);o.position.set((x1+x2)/2,.045,(z1+z2)/2);o.rotation.y=-Math.atan2(dz,dx);scene.add(o);}
  line(-90,-56,90,-56);line(-90,56,90,56);line(-90,-56,-90,56);line(90,-56,90,56);line(0,-56,0,56);
  const circle=new THREE.Mesh(new THREE.RingGeometry(9.05,9.22,80),white);circle.rotation.x=-Math.PI/2;circle.position.y=.05;scene.add(circle);
  function boxMark(x,z,w,d){line(x-w/2,z-d/2,x+w/2,z-d/2);line(x-w/2,z+d/2,x+w/2,z+d/2);line(x-w/2,z-d/2,x-w/2,z+d/2);line(x+w/2,z-d/2,x+w/2,z+d/2);}
  boxMark(-74,0,32,64);boxMark(74,0,32,64);boxMark(-84,0,12,30);boxMark(84,0,12,30);
  const goalMat=new THREE.MeshStandardMaterial({color:0xf7f8f4,metalness:.08,roughness:.42});
  const netMat=new THREE.LineBasicMaterial({color:0xe8edf0,transparent:true,opacity:.62});
  function makeGoal(x){
    const g=new THREE.Group();g.position.x=x;scene.add(g);
    const width=7.32,height=2.45,depth=3.2,back=x<0?-depth:depth;
    // Chỉ dựng bộ khung cầu môn thật: hai cột dọc và một xà ngang.
    for(const z of [-width/2,width/2]){
      const post=new THREE.Mesh(new THREE.CylinderGeometry(.105,.105,height,12),goalMat);
      post.position.set(0,height/2,z);post.castShadow=true;g.add(post);
      const rear=new THREE.Mesh(new THREE.CylinderGeometry(.055,.055,height,8),goalMat);
      rear.position.set(back,height/2,z);g.add(rear);
      const sideTop=new THREE.Mesh(new THREE.CylinderGeometry(.055,.055,depth,8),goalMat);
      sideTop.rotation.z=Math.PI/2;sideTop.position.set(back/2,height,z);g.add(sideTop);
      const sideBottom=new THREE.Mesh(new THREE.CylinderGeometry(.045,.045,depth,8),goalMat);
      sideBottom.rotation.z=Math.PI/2;sideBottom.position.set(back/2,.08,z);g.add(sideBottom);
    }
    const bar=new THREE.Mesh(new THREE.CylinderGeometry(.105,.105,width,12),goalMat);
    bar.rotation.x=Math.PI/2;bar.position.y=height;bar.castShadow=true;g.add(bar);
    // Lưới là các sợi mảnh, không dùng BoxGeometry wireframe (dễ tạo cảm giác hai khối xám lồi ra).
    const pts=[];
    const add=(a,b)=>{pts.push(a[0],a[1],a[2],b[0],b[1],b[2]);};
    const cols=18,rows=7;
    for(let i=0;i<=cols;i++){
      const z=-width/2+width*i/cols;
      add([back,0,z],[back,height,z]);
      add([back,height,z],[0,height,z]);
    }
    for(let j=0;j<=rows;j++){
      const y=height*j/rows;
      add([back,y,-width/2],[back,y,width/2]);
      add([back,y,-width/2],[0,y,-width/2]);
      add([back,y,width/2],[0,y,width/2]);
    }
    for(let i=0;i<=8;i++){
      const z=-width/2+width*i/8;
      add([0,height,z],[back,height,z]);
    }
    const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pts,3));
    g.add(new THREE.LineSegments(geo,netMat));
  }
  makeGoal(-90);makeGoal(90);
  // Keep the playable camera view clean: no oversized stands or crowd meshes overlapping the pitch.


  // Lightweight stylized players: 11 per side, with a clearly marked controlled player.
  const players=[];
  const homeFormation=[[-66,0],[-45,-36],[-45,-12],[-45,12],[-45,36],[-20,-31],[-20,0],[-20,31],[10,-33],[16,0],[10,33]];
  const awayFormation=[[66,0],[45,-36],[45,-12],[45,12],[45,36],[20,-31],[20,0],[20,31],[-10,-33],[-16,0],[-10,33]];
  function makePlayer(team,index,x,z){
    const group=new THREE.Group();group.position.set(x,0,z);scene.add(group);
    const shirt=new THREE.MeshStandardMaterial({color:team===0?0x2468d8:0xd83c38,roughness:.72});
    const shorts=new THREE.MeshStandardMaterial({color:team===0?0x102b61:0x7a1720,roughness:.8});
    const skin=new THREE.MeshStandardMaterial({color:0xc58b65});
    const torso=new THREE.Mesh(new THREE.CylinderGeometry(.42,.52,.95,10),shirt);torso.position.y=1.25;torso.castShadow=true;group.add(torso);
    const head=new THREE.Mesh(new THREE.SphereGeometry(.27,12,10),skin);head.position.y=2.02;head.castShadow=true;group.add(head);
    const shortsMesh=new THREE.Mesh(new THREE.BoxGeometry(.72,.35,.48),shorts);shortsMesh.position.y=.68;group.add(shortsMesh);
    for(const side of [-1,1]){const leg=new THREE.Mesh(new THREE.CylinderGeometry(.12,.14,.65,8),shorts);leg.position.set(side*.19,.32,0);group.add(leg);}
    const marker=new THREE.Mesh(new THREE.ConeGeometry(.2,.35,12),new THREE.MeshBasicMaterial({color:0xffe45c}));marker.position.y=2.55;marker.visible=false;group.add(marker);
    const p={group,team,index,home:new THREE.Vector3(x,0,z),velocity:new THREE.Vector3(),marker,controlled:false,stamina:100};players.push(p);return p;
  }
  homeFormation.forEach((p,i)=>makePlayer(0,i,p[0],p[1]));awayFormation.forEach((p,i)=>makePlayer(1,i,p[0],p[1]));
  let controlledPlayer=players[9];controlledPlayer.controlled=true;controlledPlayer.marker.visible=true;
  const ball=new THREE.Mesh(new THREE.SphereGeometry(.48,20,16),new THREE.MeshStandardMaterial({color:0xf7f7f2,roughness:.5}));ball.position.set(controlledPlayer.group.position.x+.9,.48,controlledPlayer.group.position.z);ball.castShadow=true;scene.add(ball);
  const ballShadow=new THREE.Mesh(new THREE.CircleGeometry(.55,20),new THREE.MeshBasicMaterial({color:0x07130c,transparent:true,opacity:.28}));ballShadow.rotation.x=-Math.PI/2;ballShadow.position.y=.025;scene.add(ballShadow);

  let paused=false,seconds=0,homeGoals=0,awayGoals=0,ballOwner=controlledPlayer,ballVel=new THREE.Vector3(),ballSpin=0,kickTimer=0,gameOver=false,sprintHeld=false,lastTouchTeam=0,ballPickupCooldown=0;
  const keys=new Set();const move=new THREE.Vector2();let lastFrame=performance.now();
  const camTarget=new THREE.Vector3();
  function updateCamera(dt){const focus=ballOwner?ballOwner.group.position:(ball.position.y>1?ball.position:controlledPlayer.group.position);const attackDir=(ballOwner?ballOwner.team:lastTouchTeam)===0?1:-1;const tx=THREE.MathUtils.clamp(focus.x,-78,78),tz=THREE.MathUtils.clamp(focus.z,-43,43);const desiredX=THREE.MathUtils.clamp(tx-attackDir*24,-84,84),desiredZ=THREE.MathUtils.clamp(tz+34,-50,50);camera.position.x=THREE.MathUtils.damp(camera.position.x,desiredX,4.5,dt);camera.position.y=THREE.MathUtils.damp(camera.position.y,34,4.5,dt);camera.position.z=THREE.MathUtils.damp(camera.position.z,desiredZ,4.5,dt);camTarget.set(THREE.MathUtils.clamp(tx+attackDir*12,-86,86),0,THREE.MathUtils.clamp(tz,-50,50));camera.lookAt(camTarget);}
  camera.position.set(-44,34,34);camera.lookAt(-8,0,0);
  function resize(){const w=mount.clientWidth,h=mount.clientHeight;if(!w||!h)return;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);}new ResizeObserver(resize).observe(mount);resize();
  function setStatus(s){statusEl.textContent=s;}
  function updateScore(){scoreEl.textContent=`${homeGoals} - ${awayGoals}`;}
  function resetPositions(){players.forEach(p=>{p.group.position.copy(p.home);p.velocity.set(0,0,0);});controlledPlayer=players[9];players.forEach(p=>{p.controlled=false;p.marker.visible=false;});controlledPlayer.controlled=true;controlledPlayer.marker.visible=true;controlledPlayer.group.position.set(-20,0,0);ballOwner=controlledPlayer;ballVel.set(0,0,0);ballPickupCooldown=0;ball.position.set(-19.1,.48,0);}
  function score(team){if(team===0)homeGoals++;else awayGoals++;updateScore();setStatus(team===0?'VÀO!!! BÀN THẮNG CHO HOME':'ĐỐI THỦ GHI BÀN');resetPositions();kickTimer=1.4;}
  function facing(){const v=new THREE.Vector3(Math.cos(controlledPlayer.group.rotation.y),0,Math.sin(controlledPlayer.group.rotation.y));if(Math.abs(v.x)+Math.abs(v.z)<.01)v.set(1,0,0);return v.normalize();}
  function kickBall(direction,speed,lift=1.2,spin=0){const dir=direction.clone();dir.y=0;if(dir.lengthSq()<0.001)dir.copy(facing());dir.normalize();ballOwner=null;ball.position.addScaledVector(dir,1.35);ball.position.y=.62;ballVel.copy(dir.multiplyScalar(speed));ballVel.y=lift;ballSpin=spin;lastTouchTeam=0;ballPickupCooldown=.48;}
  function passBall(){if(paused||gameOver||ballOwner!==controlledPlayer)return;const mates=players.filter(p=>p.team===0&&p!==controlledPlayer&&p.index!==0).map(p=>({p,score:p.group.position.distanceTo(controlledPlayer.group.position)+Math.max(0,controlledPlayer.group.position.x-p.group.position.x)*.8})).sort((a,b)=>a.score-b.score);const mate=mates[0]?.p;if(!mate)return;const dir=mate.group.position.clone().sub(ball.position);dir.y=0;kickBall(dir,20,1.0);setStatus('CHUYỀN NGẮN');}
  function throughBall(){if(paused||gameOver||ballOwner!==controlledPlayer)return;const forward=facing();const runners=players.filter(p=>p.team===0&&p!==controlledPlayer&&p.index>=8).sort((a,b)=>b.group.position.x-a.group.position.x);const runner=runners[0];let target=runner?runner.group.position.clone().add(new THREE.Vector3(8,0,runner.velocity.z*1.2)):controlledPlayer.group.position.clone().addScaledVector(forward,24);const dir=target.sub(ball.position);dir.y=0;kickBall(dir,27,1.35);setStatus('CHỌC KHE!');}
  function longBall(){if(paused||gameOver||ballOwner!==controlledPlayer)return;const dir=facing();dir.z+= (Math.random()-.5)*.18;kickBall(dir,32,8.5,.08);setStatus('CHUYỀN DÀI');}
  function shootBall(){if(paused||gameOver||ballOwner!==controlledPlayer)return;const goal=new THREE.Vector3(90,0,0);const dir=goal.sub(ball.position);dir.z+=controlledPlayer.group.position.z*.10;kickBall(dir,42,4.8,.12);setStatus('SÚT!!!');}
  function tackle(){if(paused||gameOver)return;const rival=players.filter(p=>p.team===1&&p.index!==0).sort((a,b)=>a.group.position.distanceTo(controlledPlayer.group.position)-b.group.position.distanceTo(controlledPlayer.group.position))[0];if(rival&&rival.group.position.distanceTo(controlledPlayer.group.position)<3.8){const chance=THREE.MathUtils.clamp(1-rival.group.position.distanceTo(controlledPlayer.group.position)/5,.18,.82);if(Math.random()<chance){ballOwner=controlledPlayer;ballVel.set(0,0,0);setStatus('TẮC BÓNG THÀNH CÔNG!');}else setStatus('ĐỐI THỦ CHE BÓNG!');}else setStatus('ÁP SÁT ĐỐI THỦ');}
  function bindHold(id,axis){const el=document.getElementById(id);if(!el)return;const on=()=>keys.add(axis),off=()=>keys.delete(axis);el.addEventListener('pointerdown',e=>{e.preventDefault();on();});['pointerup','pointerleave','pointercancel'].forEach(ev=>el.addEventListener(ev,off));}
  bindHold('fbm-up','ArrowUp');bindHold('fbm-down','ArrowDown');bindHold('fbm-left','ArrowLeft');bindHold('fbm-right','ArrowRight');
  document.getElementById('fbm-pass').addEventListener('click',passBall);document.getElementById('fbm-through').addEventListener('click',throughBall);document.getElementById('fbm-long').addEventListener('click',longBall);document.getElementById('fbm-shoot').addEventListener('click',shootBall);document.getElementById('fbm-tackle').addEventListener('click',tackle);const sprintBtn=document.getElementById('fbm-sprint');sprintBtn.addEventListener('pointerdown',e=>{e.preventDefault();sprintHeld=true;});['pointerup','pointerleave','pointercancel'].forEach(ev=>sprintBtn.addEventListener(ev,()=>sprintHeld=false));
  window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(['arrowup','arrowdown','arrowleft','arrowright',' '].includes(k))e.preventDefault();keys.add(k);if(k==='j')passBall();if(k==='i')throughBall();if(k==='o')longBall();if(k==='k')shootBall();if(k==='l')tackle();if(k==='shift')sprintHeld=true;});window.addEventListener('keyup',e=>{keys.delete(e.key.toLowerCase());if(e.key==='Shift')sprintHeld=false;});
  pauseBtn.addEventListener('click',()=>{paused=!paused;pauseBtn.textContent=paused?'TIẾP TỤC':'TẠM DỪNG';setStatus(paused?'ĐÃ TẠM DỪNG':'TRẬN ĐẤU ĐANG DIỄN RA');});
  restartBtn.addEventListener('click',()=>{homeGoals=0;awayGoals=0;seconds=0;gameOver=false;paused=false;updateScore();clockEl.textContent='00:00';pauseBtn.textContent='TẠM DỪNG';resetPositions();setStatus('TRẬN ĐẤU BẮT ĐẦU');});

  function animate(now){requestAnimationFrame(animate);const dt=Math.min((now-lastFrame)/1000,.04);lastFrame=now;
    if(!paused&&!gameOver){seconds+=dt*4;const mm=String(Math.floor(seconds/60)).padStart(2,'0'),ss=String(Math.floor(seconds%60)).padStart(2,'0');clockEl.textContent=`${mm}:${ss}`;if(seconds>=90){gameOver=true;setStatus('HẾT GIỜ');}
      if(kickTimer>0)kickTimer-=dt;if(ballPickupCooldown>0)ballPickupCooldown=Math.max(0,ballPickupCooldown-dt);
      const forward=(keys.has('w')||keys.has('arrowup')?1:0)-(keys.has('s')||keys.has('arrowdown')?1:0);
      const side=(keys.has('d')||keys.has('arrowright')?1:0)-(keys.has('a')||keys.has('arrowleft')?1:0);
      const direction=new THREE.Vector3(side,0,-forward).normalize();
      const hasInput=direction.lengthSq()>0;const maxSpeed=sprintHeld&&controlledPlayer.stamina>1?19:12.5;
      const desired=direction.clone().multiplyScalar(hasInput?maxSpeed:0);const accel=hasInput?8.5:5.5;
      controlledPlayer.velocity.lerp(desired,1-Math.exp(-accel*dt));
      if(hasInput){controlledPlayer.group.rotation.y=THREE.MathUtils.damp(controlledPlayer.group.rotation.y,Math.atan2(direction.x,direction.z),10,dt);}
      controlledPlayer.group.position.addScaledVector(controlledPlayer.velocity,dt);
      controlledPlayer.stamina=THREE.MathUtils.clamp(controlledPlayer.stamina+(sprintHeld&&hasInput?-14:7)*dt,0,100);
      // Tactical AI v2: role/lane based positioning. Only selected pressers chase the ball.
      const carrierPos = ballOwner ? ballOwner.group.position : ball.position;
      const ballX = carrierPos.x, ballZ = carrierPos.z;
      const possessionTeam = ballOwner ? ballOwner.team : lastTouchTeam;
      const homeHasBall = possessionTeam === 0, awayHasBall = possessionTeam === 1;
      const roleOf = i => i===0?'GK':i<=4?'DEF':i<=7?'MID':'FWD';
      const clampX=(v)=>THREE.MathUtils.clamp(v,-86,86), clampZ=(v)=>THREE.MathUtils.clamp(v,-51,51);
      const distToBall=p=>p.group.position.distanceTo(carrierPos);
      const homePressers = players.filter(q=>q.team===0 && q.index!==0 && q!==controlledPlayer).sort((a,b)=>distToBall(a)-distToBall(b)).slice(0,2);
      const awayPressers = players.filter(q=>q.team===1 && q.index!==0).sort((a,b)=>distToBall(a)-distToBall(b)).slice(0,2);
      for(const p of players){
        if(p===controlledPlayer) continue;
        const role=roleOf(p.index), dir=p.team===0?1:-1;
        const ownBall=possessionTeam===p.team, opponentBall=possessionTeam!==p.team;
        const target=p.home.clone();
        const relX=ballX*dir; // positive means ball is advanced into this team's attacking half
        const lateral=THREE.MathUtils.clamp(ballZ*.30,-15,15);
        if(role==='GK'){
          target.x=dir===1?-78:78;
          target.z=THREE.MathUtils.clamp(ballZ*.16,-9,9);
        } else if(ownBall){
          // Team in possession advances in layers, while preserving width and spacing.
          if(role==='DEF'){
            target.x += THREE.MathUtils.clamp(relX*.10,-5,13);
            target.z += p.index===1||p.index===4?lateral*.55:ballZ*.10;
          } else if(role==='MID'){
            target.x += THREE.MathUtils.clamp(relX*.22,-7,20);
            target.z += (p.index===5||p.index===7)?lateral*.8:ballZ*.22;
          } else {
            target.x += THREE.MathUtils.clamp(relX*.20,-5,25);
            target.z += p.index===9?ballZ*.12:(p.home.z<0?-1:1)*Math.max(0,8-Math.abs(ballZ)*.12);
            if(p.index===9) target.x += 7; // central striker threatens space behind
          }
        } else {
          // Out of possession: compact defensive block, not a team-wide swarm.
          const retreat=THREE.MathUtils.clamp((relX+12)*.16,0,15);
          if(role==='DEF'){
            target.x -= dir*retreat;
            target.z += THREE.MathUtils.clamp(ballZ*.18,-9,9);
          } else if(role==='MID'){
            target.x -= dir*(retreat*.72);
            target.z += THREE.MathUtils.clamp(ballZ*.24,-11,11);
          } else {
            target.x -= dir*4;
            target.z += THREE.MathUtils.clamp(ballZ*.12,-7,7);
          }
          const pressers=p.team===0?homePressers:awayPressers;
          if(role!=='GK' && pressers.includes(p)){
            target.x=ballX-dir*2.8;
            target.z=ballZ+(p.index%2?3.5:-3.5);
          }
        }
        target.x=clampX(target.x); target.z=clampZ(target.z);
        const delta=target.sub(p.group.position);
        const speed=role==='GK'?5.0:role==='MID'?7.0:role==='DEF'?5.8:7.4;
        const desiredAI=delta.length()>.35?delta.clone().normalize().multiplyScalar(Math.min(speed,delta.length()*1.65)):new THREE.Vector3();
        p.velocity.lerp(desiredAI,1-Math.exp(-3.8*dt));
        p.group.position.addScaledVector(p.velocity,dt);
        if(delta.length()>.5) p.group.rotation.y=THREE.MathUtils.damp(p.group.rotation.y,Math.atan2(delta.x,delta.z),5,dt);
      }
      if(ballOwner){const bp=ballOwner.group.position;const fwd=new THREE.Vector3(Math.cos(ballOwner.group.rotation.y),0,Math.sin(ballOwner.group.rotation.y));const touchDistance=ballOwner===controlledPlayer&&keys.size?1.05:.78;ball.position.copy(bp).addScaledVector(fwd,touchDistance);ball.position.y=.48;ballVel.copy(ballOwner.velocity).multiplyScalar(.18);}else{
        // Lightweight arcade football physics: gravity, bounce, rolling friction and spin.
        ballVel.y-=19.5*dt;ball.position.addScaledVector(ballVel,dt);ball.rotation.x+=ballVel.z*dt*.55;ball.rotation.z-=ballVel.x*dt*.55;
        if(ball.position.y<.48){ball.position.y=.48;if(Math.abs(ballVel.y)>2.0)ballVel.y=-ballVel.y*.38;else ballVel.y=0;const rolling=Math.pow(.982,dt*60);ballVel.x*=rolling;ballVel.z*=rolling;ballVel.y*=.25;}
        ballVel.x*=Math.pow(.997,dt*60);ballVel.z*=Math.pow(.997,dt*60);ballVel.x+=-ballVel.z*ballSpin*dt;ballSpin*=Math.pow(.94,dt*60);
        if(ball.position.x>88.5&&Math.abs(ball.position.z)<3.8&&ball.position.y<2.6)score(0);else if(ball.position.x< -88.5&&Math.abs(ball.position.z)<3.8&&ball.position.y<2.6)score(1);else if(ball.position.x>90||ball.position.x< -90||Math.abs(ball.position.z)>57){ball.position.set(0,.48,0);ballVel.set(0,0,0);setStatus('BÓNG RA NGOÀI');}}
      // Player-to-player body contact prevents players simply passing through one another.
      for(let i=0;i<players.length;i++){for(let j=i+1;j<players.length;j++){const a=players[i],b=players[j];const dx=b.group.position.x-a.group.position.x,dz=b.group.position.z-a.group.position.z,dist=Math.hypot(dx,dz);if(dist>0&&dist<1.25){const push=(1.25-dist)*.5, nx=dx/dist,nz=dz/dist;a.group.position.x-=nx*push;a.group.position.z-=nz*push;b.group.position.x+=nx*push;b.group.position.z+=nz*push;}}}

      if(!ballOwner&&ballPickupCooldown<=0){const nearest=players.filter(p=>p.index!==0).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position))[0];if(nearest&&nearest.group.position.distanceTo(ball.position)<1.25){ballOwner=nearest;ballVel.set(0,0,0);setStatus(nearest.team===0?'ĐỘI NHÀ GIỮ BÓNG':'ĐỐI THỦ GIỮ BÓNG');}}
      const opponent=players.filter(p=>p.team===1).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position))[0];if(opponent&&opponent.group.position.distanceTo(ball.position)<1.35&&ballOwner?.team===0){ballOwner=opponent;setStatus('ĐỐI THỦ CƯỚP BÓNG');}
      if(ballOwner?.team===1){const closest=players.filter(p=>p.team===0&&p.index!==0).sort((a,b)=>a.group.position.distanceTo(ballOwner.group.position)-b.group.position.distanceTo(ballOwner.group.position))[0];if(closest&&closest!==controlledPlayer){controlledPlayer.controlled=false;controlledPlayer.marker.visible=false;controlledPlayer=closest;controlledPlayer.controlled=true;controlledPlayer.marker.visible=true;setStatus('TỰ ĐỘNG ĐỔI SANG CẦU THỦ GẦN BÓNG NHẤT');}}
    }
    ballShadow.position.x=ball.position.x;ballShadow.position.z=ball.position.z;updateCamera(dt);renderer.render(scene,camera);
  }
  setStatus('WASD DI CHUYỂN · SHIFT TĂNG TỐC · J/I/O/K CHUYỀN VÀ SÚT');requestAnimationFrame(animate);
} catch(err){console.error('FBM 3D match error:',err);errorBox.hidden=false;}
