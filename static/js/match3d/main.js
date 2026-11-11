import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js';

const mount = document.getElementById('fbm3d-canvas');
const errorBox = document.getElementById('fbm3d-error');

try {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x91b6c2);
  scene.fog = new THREE.Fog(0x91b6c2, 105, 220);

  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
  let cameraYaw = 0;
  let cameraDistance = 105;
  let cameraHeight = 72;

  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12;
  mount.appendChild(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xe8f5ff, 0x31523a, 2.0));
  const sun = new THREE.DirectionalLight(0xfff1d6, 2.6);
  sun.position.set(-35, 65, 28);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -75; sun.shadow.camera.right = 75;
  sun.shadow.camera.top = 65; sun.shadow.camera.bottom = -65;
  scene.add(sun);

  const ground = new THREE.Mesh(new THREE.PlaneGeometry(230, 170), new THREE.MeshStandardMaterial({ color: 0x183b2b, roughness: 1 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -0.18; ground.receiveShadow = true; scene.add(ground);

  const field = new THREE.Mesh(new THREE.PlaneGeometry(105, 68), new THREE.MeshStandardMaterial({ color: 0x267b43, roughness: 0.95 }));
  field.rotation.x = -Math.PI / 2; field.position.y = 0; field.receiveShadow = true; scene.add(field);

  // Alternating mowing stripes.
  for (let i = 0; i < 10; i++) {
    const stripe = new THREE.Mesh(new THREE.PlaneGeometry(10.5, 68), new THREE.MeshStandardMaterial({ color: i % 2 ? 0x2b8548 : 0x24753f, roughness: 1 }));
    stripe.rotation.x = -Math.PI / 2; stripe.position.set(-47.25 + i * 10.5, 0.012, 0); scene.add(stripe);
  }

  const lineMat = new THREE.MeshBasicMaterial({ color: 0xf4f5e9 });
  function line(x1,z1,x2,z2,width=0.16) {
    const dx=x2-x1, dz=z2-z1, len=Math.hypot(dx,dz);
    const mesh=new THREE.Mesh(new THREE.BoxGeometry(len,width,0.035),lineMat);
    mesh.position.set((x1+x2)/2,0.045,(z1+z2)/2);
    mesh.rotation.y=-Math.atan2(dz,dx);
    scene.add(mesh);
  }
  // Outer boundary and halfway line.
  line(-52.5,-34,52.5,-34); line(-52.5,34,52.5,34);
  line(-52.5,-34,-52.5,34); line(52.5,-34,52.5,34);
  line(0,-34,0,34);
  const circle = new THREE.Mesh(new THREE.RingGeometry(9.05,9.22,80),lineMat);
  circle.rotation.x=-Math.PI/2; circle.position.y=.05; scene.add(circle);
  const spot = new THREE.Mesh(new THREE.CircleGeometry(.22,24),lineMat);
  spot.rotation.x=-Math.PI/2; spot.position.set(0,.052,0); scene.add(spot);
  function boxMark(x,z,w,d) {
    const a=new THREE.Mesh(new THREE.BoxGeometry(w,.035,.16),lineMat); a.position.set(x,.05,z); scene.add(a);
    const b=new THREE.Mesh(new THREE.BoxGeometry(.16,.035,d),lineMat); b.position.set(x+(x<0?w/2:-w/2),.05,z); scene.add(b);
    const c=new THREE.Mesh(new THREE.BoxGeometry(w,.035,.16),lineMat); c.position.set(x,.05,z+(z<0?d/2:-d/2)); scene.add(c);
  }
  boxMark(-43.5,0,18,40.3); boxMark(43.5,0,18,40.3);
  boxMark(-49,0,6.5,18.3); boxMark(49,0,6.5,18.3);

  // Simplified goals.
  const goalMat = new THREE.MeshStandardMaterial({ color: 0xf0f2ed, metalness:.25, roughness:.45 });
  function goal(x, direction) {
    const group=new THREE.Group(); group.position.set(x,0,0); scene.add(group);
    const width=7.32, height=2.45, depth=3.2;
    for (const z of [-width/2,width/2]) {
      const post=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,height,12),goalMat);
      post.position.set(0,height/2,z); post.castShadow=true; group.add(post);
    }
    const bar=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,width,12),goalMat);
    bar.rotation.x=Math.PI/2; bar.position.set(0,height,0); bar.castShadow=true; group.add(bar);
    const net=new THREE.Mesh(new THREE.BoxGeometry(depth,height,width),new THREE.MeshBasicMaterial({color:0xe9f3ed,wireframe:true,transparent:true,opacity:.2}));
    net.position.x=direction*depth/2; net.position.y=height/2; group.add(net);
  }
  goal(-52.5,-1); goal(52.5,1);

  // Stylized stadium seating bowls around the pitch.
  const standMat1=new THREE.MeshStandardMaterial({color:0x334b55,roughness:.9});
  const standMat2=new THREE.MeshStandardMaterial({color:0x536873,roughness:.9});
  function stand(w,d,x,z,rot=0) {
    const group=new THREE.Group(); group.position.set(x,0,z); group.rotation.y=rot; scene.add(group);
    for(let i=0;i<5;i++) {
      const tier=new THREE.Mesh(new THREE.BoxGeometry(w+i*3,1.8,d/5),i%2?standMat1:standMat2);
      tier.position.set(0,1+i*1.65, i*2.2); tier.castShadow=true; tier.receiveShadow=true; group.add(tier);
    }
  }
  stand(112,18,0,-48); stand(112,18,0,48,Math.PI);
  stand(75,18,-67,0,-Math.PI/2); stand(75,18,67,0,Math.PI/2);

  // Tiny abstract crowd dots add stadium scale without heavy models.
  const crowdGeo=new THREE.BufferGeometry(), crowd=[];
  for(let i=0;i<1700;i++) {
    const side=i%4, t=Math.random();
    let x,z;
    if(side===0||side===1){x=(t-.5)*112;z=side===0?-48:48;}
    else{x=side===2?-67:67;z=(t-.5)*75;}
    crowd.push(x,2+Math.random()*7,z);
  }
  crowdGeo.setAttribute('position',new THREE.Float32BufferAttribute(crowd,3));
  const crowdPoints=new THREE.Points(crowdGeo,new THREE.PointsMaterial({color:0xd7dedb,size:.65,sizeAttenuation:true}));
  scene.add(crowdPoints);

  // Ball placed at the centre as a scale reference.
  const ball=new THREE.Mesh(new THREE.SphereGeometry(.48,24,16),new THREE.MeshStandardMaterial({color:0xf7f7f2,roughness:.55}));
  ball.position.set(0,.55,0); ball.castShadow=true; scene.add(ball);

  const target=new THREE.Vector3(0,0,0);
  function updateCamera() {
    camera.position.set(Math.sin(cameraYaw)*cameraDistance,cameraHeight,Math.cos(cameraYaw)*cameraDistance);
    camera.lookAt(target);
  }
  updateCamera();

  let dragging=false, lastX=0, lastY=0;
  renderer.domElement.addEventListener('pointerdown',e=>{dragging=true;lastX=e.clientX;lastY=e.clientY;renderer.domElement.setPointerCapture(e.pointerId);});
  renderer.domElement.addEventListener('pointermove',e=>{
    if(!dragging)return;
    cameraYaw-=(e.clientX-lastX)*.004;
    cameraHeight=Math.max(35,Math.min(100,cameraHeight+(e.clientY-lastY)*.18));
    lastX=e.clientX;lastY=e.clientY;updateCamera();
  });
  renderer.domElement.addEventListener('pointerup',()=>dragging=false);
  renderer.domElement.addEventListener('pointercancel',()=>dragging=false);
  renderer.domElement.addEventListener('wheel',e=>{
    cameraDistance=Math.max(70,Math.min(145,cameraDistance+e.deltaY*.06));
    updateCamera();
  },{passive:true});

  function resize() {
    const w=mount.clientWidth, h=mount.clientHeight;
    if(!w||!h)return;
    camera.aspect=w/h; camera.updateProjectionMatrix(); renderer.setSize(w,h,false);
  }
  new ResizeObserver(resize).observe(mount); resize();
  function animate() {
    requestAnimationFrame(animate);
    ball.rotation.x+=.003; ball.rotation.z+=.004;
    renderer.render(scene,camera);
  }
  animate();
} catch (err) {
  console.error('FBM 3D demo error:',err);
  errorBox.hidden=false;
}
