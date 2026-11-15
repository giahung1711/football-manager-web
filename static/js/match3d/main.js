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
  const field = new THREE.Mesh(new THREE.PlaneGeometry(140,90),new THREE.MeshStandardMaterial({color:0x267b43,roughness:.95})); field.rotation.x=-Math.PI/2; field.receiveShadow=true; scene.add(field);
  for(let i=0;i<10;i++){const m=new THREE.Mesh(new THREE.PlaneGeometry(14,90),new THREE.MeshStandardMaterial({color:i%2?0x2b8548:0x24753f}));m.rotation.x=-Math.PI/2;m.position.set(-63+i*14,.012,0);scene.add(m);}
  const white=new THREE.MeshBasicMaterial({color:0xf4f5e9});
  function line(x1,z1,x2,z2,w=.15){const dx=x2-x1,dz=z2-z1,len=Math.hypot(dx,dz);const o=new THREE.Mesh(new THREE.BoxGeometry(len,w,.035),white);o.position.set((x1+x2)/2,.045,(z1+z2)/2);o.rotation.y=-Math.atan2(dz,dx);scene.add(o);}
  line(-70,-45,70,-45);line(-70,45,70,45);line(-70,-45,-70,45);line(70,-45,70,45);line(0,-45,0,45);
  const circle=new THREE.Mesh(new THREE.RingGeometry(9.05,9.22,80),white);circle.rotation.x=-Math.PI/2;circle.position.y=.05;scene.add(circle);
  function boxMark(x,z,w,d){line(x-w/2,z-d/2,x+w/2,z-d/2);line(x-w/2,z+d/2,x+w/2,z+d/2);line(x-w/2,z-d/2,x-w/2,z+d/2);line(x+w/2,z-d/2,x+w/2,z+d/2);}
  boxMark(-57,0,24,52);boxMark(57,0,24,52);boxMark(-65,0,8,24);boxMark(65,0,8,24);
  const goalMat=new THREE.MeshStandardMaterial({color:0xf0f2ed,metalness:.2,roughness:.45});
  function makeGoal(x){const g=new THREE.Group();g.position.x=x;scene.add(g);const width=7.32,height=2.45,depth=3.2;for(const z of [-width/2,width/2]){const p=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,height,10),goalMat);p.position.set(0,height/2,z);g.add(p);}const bar=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,width,10),goalMat);bar.rotation.x=Math.PI/2;bar.position.y=height;g.add(bar);const net=new THREE.Mesh(new THREE.BoxGeometry(depth,height,width),new THREE.MeshBasicMaterial({color:0xffffff,wireframe:true,transparent:true,opacity:.18}));net.position.set(x<0?-depth/2:depth/2,height/2,0);g.add(net);}
  makeGoal(-70);makeGoal(70);
  const standMat=new THREE.MeshStandardMaterial({color:0x405964,roughness:.9});
  for(const [x,z,rot] of [[0,-62,0],[0,62,Math.PI],[-82,0,-Math.PI/2],[82,0,Math.PI/2]]){const g=new THREE.Group();g.position.set(x,0,z);g.rotation.y=rot;scene.add(g);for(let i=0;i<5;i++){const s=new THREE.Mesh(new THREE.BoxGeometry(x===0?150+i*3:24,1.7,x===0?24:100+i*3),standMat);s.position.set(0,1+i*1.55,0);g.add(s);}}
  const crowdGeo=new THREE.BufferGeometry(),crowd=[];for(let i=0;i<1500;i++){const side=i%4,t=Math.random();let x,z;if(side<2){x=(t-.5)*150;z=side===0?-62:62;}else{x=side===2?-82:82;z=(t-.5)*100;}crowd.push(x,2+Math.random()*7,z);}crowdGeo.setAttribute('position',new THREE.Float32BufferAttribute(crowd,3));scene.add(new THREE.Points(crowdGeo,new THREE.PointsMaterial({color:0xe1e6e2,size:.55})));

  // Lightweight stylized players: 11 per side, with a clearly marked controlled player.
  const players=[];
  const homeFormation=[[-52,0],[-36,-29],[-36,-10],[-36,10],[-36,29],[-16,-25],[-16,0],[-16,25],[8,-26],[12,0],[8,26]];
  const awayFormation=[[52,0],[36,-29],[36,-10],[36,10],[36,29],[16,-25],[16,0],[16,25],[-8,-26],[-12,0],[-8,26]];
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
    const p={group,team,index,home:new THREE.Vector3(x,0,z),velocity:new THREE.Vector3(),marker,controlled:false};players.push(p);return p;
  }
  homeFormation.forEach((p,i)=>makePlayer(0,i,p[0],p[1]));awayFormation.forEach((p,i)=>makePlayer(1,i,p[0],p[1]));
  let controlledPlayer=players[9];controlledPlayer.controlled=true;controlledPlayer.marker.visible=true;
  const ball=new THREE.Mesh(new THREE.SphereGeometry(.48,20,16),new THREE.MeshStandardMaterial({color:0xf7f7f2,roughness:.5}));ball.position.set(controlledPlayer.group.position.x+.9,.48,controlledPlayer.group.position.z);ball.castShadow=true;scene.add(ball);
  const ballShadow=new THREE.Mesh(new THREE.CircleGeometry(.55,20),new THREE.MeshBasicMaterial({color:0x07130c,transparent:true,opacity:.28}));ballShadow.rotation.x=-Math.PI/2;ballShadow.position.y=.025;scene.add(ballShadow);

  let paused=false,seconds=0,homeGoals=0,awayGoals=0,ballOwner=controlledPlayer,ballVel=new THREE.Vector3(),kickTimer=0,gameOver=false;
  const keys=new Set();const move=new THREE.Vector2();let lastFrame=performance.now();
  const camTarget=new THREE.Vector3();
  function updateCamera(dt){const focus=ballOwner?ballOwner.group.position:ball.position;const followX=THREE.MathUtils.clamp(focus.x*.72,-42,42);const fixedX=THREE.MathUtils.damp(camera.position.x,followX,2.2,dt);camera.position.set(fixedX,82,108);camTarget.set(fixedX,0,0);camera.lookAt(camTarget);}
  camera.position.set(0,82,108);camera.lookAt(0,0,0);
  function resize(){const w=mount.clientWidth,h=mount.clientHeight;if(!w||!h)return;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);}new ResizeObserver(resize).observe(mount);resize();
  function setStatus(s){statusEl.textContent=s;}
  function updateScore(){scoreEl.textContent=`${homeGoals} - ${awayGoals}`;}
  function resetPositions(){players.forEach(p=>{p.group.position.copy(p.home);p.velocity.set(0,0,0);});controlledPlayer=players[9];players.forEach(p=>{p.controlled=false;p.marker.visible=false;});controlledPlayer.controlled=true;controlledPlayer.marker.visible=true;controlledPlayer.group.position.set(-16,0,0);ballOwner=controlledPlayer;ballVel.set(0,0,0);ball.position.set(-15.1,.48,0);}
  function score(team){if(team===0)homeGoals++;else awayGoals++;updateScore();setStatus(team===0?'VÀO!!! BÀN THẮNG CHO HOME':'ĐỐI THỦ GHI BÀN');resetPositions();kickTimer=1.4;}
  function passBall(){if(paused||gameOver)return;const mate=players.filter(p=>p.team===0&&p!==controlledPlayer).sort((a,b)=>a.group.position.distanceTo(controlledPlayer.group.position)-b.group.position.distanceTo(controlledPlayer.group.position))[0];if(!mate)return;const dir=mate.group.position.clone().sub(ball.position).normalize();ballOwner=null;ballVel.copy(dir.multiplyScalar(24));setStatus('ĐÃ CHUYỀN BÓNG');}
  function shootBall(){if(paused||gameOver)return;const dir=new THREE.Vector3(1,0,0);dir.z=-controlledPlayer.group.position.z*.025;dir.normalize();ballOwner=null;ballVel.set(34,9,dir.z*8);setStatus('SÚT!!!');}
  function tackle(){if(paused||gameOver)return;const rival=players.filter(p=>p.team===1).sort((a,b)=>a.group.position.distanceTo(controlledPlayer.group.position)-b.group.position.distanceTo(controlledPlayer.group.position))[0];if(rival&&rival.group.position.distanceTo(controlledPlayer.group.position)<4.2){ballOwner=controlledPlayer;ballVel.set(0,0,0);setStatus('ĐÃ TRANH ĐƯỢC BÓNG!');}else setStatus('ÁP SÁT ĐỐI THỦ');}
  function bindHold(id,axis){const el=document.getElementById(id);if(!el)return;const on=()=>keys.add(axis),off=()=>keys.delete(axis);el.addEventListener('pointerdown',e=>{e.preventDefault();on();});['pointerup','pointerleave','pointercancel'].forEach(ev=>el.addEventListener(ev,off));}
  bindHold('fbm-up','ArrowUp');bindHold('fbm-down','ArrowDown');bindHold('fbm-left','ArrowLeft');bindHold('fbm-right','ArrowRight');
  document.getElementById('fbm-pass').addEventListener('click',passBall);document.getElementById('fbm-shoot').addEventListener('click',shootBall);document.getElementById('fbm-tackle').addEventListener('click',tackle);
  window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(['arrowup','arrowdown','arrowleft','arrowright',' '].includes(k))e.preventDefault();keys.add(k);if(k==='j')passBall();if(k==='k')shootBall();if(k==='l')tackle();});window.addEventListener('keyup',e=>keys.delete(e.key.toLowerCase()));
  pauseBtn.addEventListener('click',()=>{paused=!paused;pauseBtn.textContent=paused?'TIẾP TỤC':'TẠM DỪNG';setStatus(paused?'ĐÃ TẠM DỪNG':'TRẬN ĐẤU ĐANG DIỄN RA');});
  restartBtn.addEventListener('click',()=>{homeGoals=0;awayGoals=0;seconds=0;gameOver=false;paused=false;updateScore();clockEl.textContent='00:00';pauseBtn.textContent='TẠM DỪNG';resetPositions();setStatus('TRẬN ĐẤU BẮT ĐẦU');});

  function animate(now){requestAnimationFrame(animate);const dt=Math.min((now-lastFrame)/1000,.04);lastFrame=now;
    if(!paused&&!gameOver){seconds+=dt*4;const mm=String(Math.floor(seconds/60)).padStart(2,'0'),ss=String(Math.floor(seconds%60)).padStart(2,'0');clockEl.textContent=`${mm}:${ss}`;if(seconds>=90){gameOver=true;setStatus('HẾT GIỜ');}
      if(kickTimer>0)kickTimer-=dt;
      const forward=(keys.has('w')||keys.has('arrowup')?1:0)-(keys.has('s')||keys.has('arrowdown')?1:0);
      const side=(keys.has('d')||keys.has('arrowright')?1:0)-(keys.has('a')||keys.has('arrowleft')?1:0);
      const direction=new THREE.Vector3(side,0,-forward).normalize();
      if(direction.lengthSq()>0){controlledPlayer.group.position.addScaledVector(direction,13*dt);controlledPlayer.group.rotation.y=Math.atan2(direction.x,direction.z);}
      controlledPlayer.group.position.x=THREE.MathUtils.clamp(controlledPlayer.group.position.x,-66,66);controlledPlayer.group.position.z=THREE.MathUtils.clamp(controlledPlayer.group.position.z,-42,42);
      // Tactical AI: players keep their lanes and roles; only the nearest defenders press.
      const ballX=ballOwner?ballOwner.group.position.x:ball.position.x;
      const ballZ=ballOwner?ballOwner.group.position.z:ball.position.z;
      const homeHasBall=ballOwner?.team===0, awayHasBall=ballOwner?.team===1;
      const roleOf=i=>i===0?'GK':i<=4?'DEF':i<=7?'MID':'FWD';
      for(const p of players){
        if(p===controlledPlayer)continue;
        const role=roleOf(p.index), sign=p.team===0?1:-1;
        const target=p.home.clone();
        if(role==='GK'){
          target.x=p.team===0?-58:58; target.z=THREE.MathUtils.clamp(ballZ*.18,-7,7);
        } else if(p.team===0){
          if(homeHasBall){
            if(role==='DEF'){target.x=p.home.x+THREE.MathUtils.clamp(ballX*.10,-5,5);target.z=p.home.z+ballZ*.10;}
            if(role==='MID'){target.x=p.home.x+THREE.MathUtils.clamp(ballX*.22,-9,9);target.z=p.home.z+ballZ*.30;}
            if(role==='FWD'){target.x=p.home.x+THREE.MathUtils.clamp(ballX*.18,-7,12);target.z=p.home.z+ballZ*.22;}
          } else if(awayHasBall){
            if(role==='DEF'){target.x=p.home.x+THREE.MathUtils.clamp(ballX*.16,-8,8);target.z=p.home.z+ballZ*.16;}
            if(role==='MID'){target.x=p.home.x+THREE.MathUtils.clamp(ballX*.28,-12,12);target.z=p.home.z+ballZ*.24;}
            if(role==='FWD'){target.x=p.home.x+2;target.z=p.home.z+ballZ*.10;}
          } else {target.x+=ballX*.08;target.z+=ballZ*.10;}
        } else {
          // Opponents hold their own formation; at most two nearest outfielders press.
          target.x=p.home.x+ballX*.10;target.z=p.home.z+ballZ*.12;
          if(homeHasBall && role!=='GK'){
            const pressers=players.filter(q=>q.team===1&&q.index!==0).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position)).slice(0,2);
            if(pressers.includes(p)){target.x=ballX+ (p.team===1?2:-2);target.z=ballZ+(p.index%2?3:-3);}
          }
          if(awayHasBall && role==='FWD'){target.x=p.home.x-3;target.z=p.home.z+ballZ*.08;}
        }
        target.x=THREE.MathUtils.clamp(target.x,-66,66);target.z=THREE.MathUtils.clamp(target.z,-41,41);
        const delta=target.sub(p.group.position);const speed=role==='GK'?4.2:role==='MID'?6.2:role==='DEF'?5.0:6.0;
        if(delta.length()>0.7){const step=Math.min(delta.length(),speed*dt);p.group.position.addScaledVector(delta.normalize(),step);p.group.rotation.y=Math.atan2(delta.x,delta.z);}
      }
      if(ballOwner){const bp=ballOwner.group.position;const offset=new THREE.Vector3(.75,.48,.45).applyAxisAngle(new THREE.Vector3(0,1,0),ballOwner.group.rotation.y);ball.position.copy(bp).add(offset);ballVel.set(0,0,0);}else{ball.position.addScaledVector(ballVel,dt);ballVel.multiplyScalar(Math.pow(.985,dt*60));ball.position.y=Math.max(.48,ball.position.y-ball.position.y*.02);if(ball.position.x>68.5&&Math.abs(ball.position.z)<3.8&&ball.position.y<2.6)score(0);else if(ball.position.x< -68.5&&Math.abs(ball.position.z)<3.8&&ball.position.y<2.6)score(1);else if(ball.position.x>70||ball.position.x< -70||Math.abs(ball.position.z)>46){ball.position.set(0,.48,0);ballVel.set(0,0,0);setStatus('BÓNG RA NGOÀI');}}
      if(!ballOwner){const nearest=players.filter(p=>p.index!==0).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position))[0];if(nearest&&nearest.group.position.distanceTo(ball.position)<1.8){ballOwner=nearest;setStatus(nearest.team===0?'ĐỘI NHÀ GIỮ BÓNG':'ĐỐI THỦ GIỮ BÓNG');}}
      const opponent=players.filter(p=>p.team===1).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position))[0];if(opponent&&opponent.group.position.distanceTo(ball.position)<1.35&&ballOwner?.team===0){ballOwner=opponent;setStatus('ĐỐI THỦ CƯỚP BÓNG');}
      if(ballOwner?.team===1){const closest=players.filter(p=>p.team===0&&p.index!==0).sort((a,b)=>a.group.position.distanceTo(ballOwner.group.position)-b.group.position.distanceTo(ballOwner.group.position))[0];if(closest&&closest!==controlledPlayer){controlledPlayer.controlled=false;controlledPlayer.marker.visible=false;controlledPlayer=closest;controlledPlayer.controlled=true;controlledPlayer.marker.visible=true;setStatus('TỰ ĐỘNG ĐỔI SANG CẦU THỦ GẦN BÓNG NHẤT');}}
    }
    ball.rotation.x+=.04;ball.rotation.z+=.03;ballShadow.position.x=ball.position.x;ballShadow.position.z=ball.position.z;updateCamera(dt);renderer.render(scene,camera);
  }
  setStatus('DÙNG WASD / PHÍM MŨI TÊN ĐỂ DI CHUYỂN');requestAnimationFrame(animate);
} catch(err){console.error('FBM 3D match error:',err);errorBox.hidden=false;}
