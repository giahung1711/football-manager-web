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
  const camera = new THREE.PerspectiveCamera(48, 1, .1, 350);
  const renderer = new THREE.WebGLRenderer({ antialias:true, powerPreference:'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.6));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping;
  mount.appendChild(renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xe9f5ff,0x31523a,2.1));
  const sun = new THREE.DirectionalLight(0xfff0d2,2.5); sun.position.set(-30,65,25); sun.castShadow=true; sun.shadow.mapSize.set(1536,1536); scene.add(sun);

  const ground = new THREE.Mesh(new THREE.PlaneGeometry(230,170),new THREE.MeshStandardMaterial({color:0x183b2b,roughness:1})); ground.rotation.x=-Math.PI/2; ground.position.y=-.2; ground.receiveShadow=true; scene.add(ground);
  const field = new THREE.Mesh(new THREE.PlaneGeometry(105,68),new THREE.MeshStandardMaterial({color:0x267b43,roughness:.95})); field.rotation.x=-Math.PI/2; field.receiveShadow=true; scene.add(field);
  for(let i=0;i<10;i++){const m=new THREE.Mesh(new THREE.PlaneGeometry(10.5,68),new THREE.MeshStandardMaterial({color:i%2?0x2b8548:0x24753f}));m.rotation.x=-Math.PI/2;m.position.set(-47.25+i*10.5,.012,0);scene.add(m);}
  const white=new THREE.MeshBasicMaterial({color:0xf4f5e9});
  function line(x1,z1,x2,z2,w=.15){const dx=x2-x1,dz=z2-z1,len=Math.hypot(dx,dz);const o=new THREE.Mesh(new THREE.BoxGeometry(len,w,.035),white);o.position.set((x1+x2)/2,.045,(z1+z2)/2);o.rotation.y=-Math.atan2(dz,dx);scene.add(o);}
  line(-52.5,-34,52.5,-34);line(-52.5,34,52.5,34);line(-52.5,-34,-52.5,34);line(52.5,-34,52.5,34);line(0,-34,0,34);
  const circle=new THREE.Mesh(new THREE.RingGeometry(9.05,9.22,80),white);circle.rotation.x=-Math.PI/2;circle.position.y=.05;scene.add(circle);
  function boxMark(x,z,w,d){line(x-w/2,z-d/2,x+w/2,z-d/2);line(x-w/2,z+d/2,x+w/2,z+d/2);line(x-w/2,z-d/2,x-w/2,z+d/2);line(x+w/2,z-d/2,x+w/2,z+d/2);}
  boxMark(-43.5,0,18,40.3);boxMark(43.5,0,18,40.3);boxMark(-49,0,6.5,18.3);boxMark(49,0,6.5,18.3);
  const goalMat=new THREE.MeshStandardMaterial({color:0xf0f2ed,metalness:.2,roughness:.45});
  function makeGoal(x){const g=new THREE.Group();g.position.x=x;scene.add(g);const width=7.32,height=2.45,depth=3.2;for(const z of [-width/2,width/2]){const p=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,height,10),goalMat);p.position.set(0,height/2,z);g.add(p);}const bar=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,width,10),goalMat);bar.rotation.x=Math.PI/2;bar.position.y=height;g.add(bar);const net=new THREE.Mesh(new THREE.BoxGeometry(depth,height,width),new THREE.MeshBasicMaterial({color:0xffffff,wireframe:true,transparent:true,opacity:.18}));net.position.set(x<0?-depth/2:depth/2,height/2,0);g.add(net);}
  makeGoal(-52.5);makeGoal(52.5);
  const standMat=new THREE.MeshStandardMaterial({color:0x405964,roughness:.9});
  for(const [x,z,rot] of [[0,-48,0],[0,48,Math.PI],[-67,0,-Math.PI/2],[67,0,Math.PI/2]]){const g=new THREE.Group();g.position.set(x,0,z);g.rotation.y=rot;scene.add(g);for(let i=0;i<5;i++){const s=new THREE.Mesh(new THREE.BoxGeometry(x===0?112+i*3:18,1.7,x===0?18:75+i*3),standMat);s.position.set(0,1+i*1.55,0);g.add(s);}}
  const crowdGeo=new THREE.BufferGeometry(),crowd=[];for(let i=0;i<1500;i++){const side=i%4,t=Math.random();let x,z;if(side<2){x=(t-.5)*112;z=side===0?-48:48;}else{x=side===2?-67:67;z=(t-.5)*75;}crowd.push(x,2+Math.random()*7,z);}crowdGeo.setAttribute('position',new THREE.Float32BufferAttribute(crowd,3));scene.add(new THREE.Points(crowdGeo,new THREE.PointsMaterial({color:0xe1e6e2,size:.55})));

  // Lightweight stylized players: 11 per side, with a clearly marked controlled player.
  const players=[];
  const homeFormation=[[-38,0],[-28,-22],[-28,-7],[-28,7],[-28,22],[-12,-19],[-12,0],[-12,19],[5,-20],[8,0],[5,20]];
  const awayFormation=[[38,0],[28,-22],[28,-7],[28,7],[28,22],[12,-19],[12,0],[12,19],[-5,-20],[-8,0],[-5,20]];
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
  const user=players[9];user.controlled=true;user.marker.visible=true;
  const ball=new THREE.Mesh(new THREE.SphereGeometry(.48,20,16),new THREE.MeshStandardMaterial({color:0xf7f7f2,roughness:.5}));ball.position.set(user.group.position.x+.9,.48,user.group.position.z);ball.castShadow=true;scene.add(ball);
  const ballShadow=new THREE.Mesh(new THREE.CircleGeometry(.55,20),new THREE.MeshBasicMaterial({color:0x07130c,transparent:true,opacity:.28}));ballShadow.rotation.x=-Math.PI/2;ballShadow.position.y=.025;scene.add(ballShadow);

  let yaw=0,paused=false,seconds=0,homeGoals=0,awayGoals=0,ballOwner=user,ballVel=new THREE.Vector3(),kickTimer=0,gameOver=false;
  const keys=new Set();const move=new THREE.Vector2();let lastFrame=performance.now();
  const camTarget=new THREE.Vector3();
  function updateCamera(dt){const pos=user.group.position;camTarget.set(pos.x*.45,0,pos.z*.45);const desired=new THREE.Vector3(pos.x+Math.sin(yaw)*24,19,pos.z+Math.cos(yaw)*29);camera.position.lerp(desired,1-Math.pow(.001,dt));camera.lookAt(camTarget);}
  function resize(){const w=mount.clientWidth,h=mount.clientHeight;if(!w||!h)return;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);}new ResizeObserver(resize).observe(mount);resize();
  function setStatus(s){statusEl.textContent=s;}
  function updateScore(){scoreEl.textContent=`${homeGoals} - ${awayGoals}`;}
  function resetPositions(){players.forEach(p=>{p.group.position.copy(p.home);p.velocity.set(0,0,0);});user.group.position.set(-12,0,0);ballOwner=user;ballVel.set(0,0,0);ball.position.set(-11.1,.48,0);ballOwner=user;}
  function score(team){if(team===0)homeGoals++;else awayGoals++;updateScore();setStatus(team===0?'VÀO!!! BÀN THẮNG CHO HOME':'ĐỐI THỦ GHI BÀN');resetPositions();kickTimer=1.4;}
  function passBall(){if(paused||gameOver)return;const mate=players.filter(p=>p.team===0&&p!==user).sort((a,b)=>a.group.position.distanceTo(user.group.position)-b.group.position.distanceTo(user.group.position))[0];if(!mate)return;const dir=mate.group.position.clone().sub(ball.position).normalize();ballOwner=null;ballVel.copy(dir.multiplyScalar(24));setStatus('ĐÃ CHUYỀN BÓNG');}
  function shootBall(){if(paused||gameOver)return;const dir=new THREE.Vector3(1,0,0);dir.z=-user.group.position.z*.025;dir.normalize();ballOwner=null;ballVel.set(34,9,dir.z*8);setStatus('SÚT!!!');}
  function tackle(){if(paused||gameOver)return;const rival=players.filter(p=>p.team===1).sort((a,b)=>a.group.position.distanceTo(user.group.position)-b.group.position.distanceTo(user.group.position))[0];if(rival&&rival.group.position.distanceTo(user.group.position)<4.2){ballOwner=user;ballVel.set(0,0,0);setStatus('ĐÃ TRANH ĐƯỢC BÓNG!');}else setStatus('ÁP SÁT ĐỐI THỦ');}
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
      const direction=new THREE.Vector3(side,0,-forward).applyAxisAngle(new THREE.Vector3(0,1,0),yaw).normalize();
      if(direction.lengthSq()>0){user.group.position.addScaledVector(direction,13*dt);user.group.rotation.y=Math.atan2(direction.x,direction.z);}
      user.group.position.x=THREE.MathUtils.clamp(user.group.position.x,-49,49);user.group.position.z=THREE.MathUtils.clamp(user.group.position.z,-31,31);
      // Teammates return toward formation and nearby opponents pressure the ball.
      for(const p of players){if(p===user)continue;let target=p.home.clone();if(p.team===1&&ballOwner&&ballOwner.team===0){target.copy(ballOwner.group.position).add(new THREE.Vector3(p.index%2?2:-2,0,(p.index%3-1)*2));}else if(p.team===0&&ballOwner===user){target.copy(user.group.position).add(new THREE.Vector3((p.index%3-1)*3,0,(p.index%2?4:-4)));}const delta=target.sub(p.group.position);if(delta.length()>1)p.group.position.addScaledVector(delta.normalize(),(p.team===1?5.5:3.5)*dt);p.group.position.x=THREE.MathUtils.clamp(p.group.position.x,-50,50);p.group.position.z=THREE.MathUtils.clamp(p.group.position.z,-32,32);}
      if(ballOwner){const bp=ballOwner.group.position;const offset=new THREE.Vector3(.75,.48,.45).applyAxisAngle(new THREE.Vector3(0,1,0),ballOwner.group.rotation.y);ball.position.copy(bp).add(offset);ballVel.set(0,0,0);}else{ball.position.addScaledVector(ballVel,dt);ballVel.multiplyScalar(Math.pow(.985,dt*60));ball.position.y=Math.max(.48,ball.position.y-ball.position.y*.02);if(ball.position.x>51.5&&Math.abs(ball.position.z)<3.8&&ball.position.y<2.6)score(0);else if(ball.position.x< -51.5&&Math.abs(ball.position.z)<3.8&&ball.position.y<2.6)score(1);else if(ball.position.x>52||ball.position.x< -52||Math.abs(ball.position.z)>34){ball.position.set(0,.48,0);ballVel.set(0,0,0);setStatus('BÓNG RA NGOÀI');}}
      if(!ballOwner){const nearest=players.filter(p=>p.team===0).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position))[0];if(nearest&&nearest.group.position.distanceTo(ball.position)<1.8){ballOwner=nearest;setStatus(nearest===user?'BẠN ĐANG CÓ BÓNG':'ĐỒNG ĐỘI ĐANG GIỮ BÓNG');}}
      const opponent=players.filter(p=>p.team===1).sort((a,b)=>a.group.position.distanceTo(ball.position)-b.group.position.distanceTo(ball.position))[0];if(opponent&&opponent.group.position.distanceTo(ball.position)<1.35&&ballOwner?.team===0){ballOwner=opponent;setStatus('ĐỐI THỦ CƯỚP BÓNG');}
    }
    ball.rotation.x+=.04;ball.rotation.z+=.03;ballShadow.position.x=ball.position.x;ballShadow.position.z=ball.position.z;updateCamera(dt);renderer.render(scene,camera);
  }
  setStatus('DÙNG WASD / PHÍM MŨI TÊN ĐỂ DI CHUYỂN');requestAnimationFrame(animate);
} catch(err){console.error('FBM 3D match error:',err);errorBox.hidden=false;}
