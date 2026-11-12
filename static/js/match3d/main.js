
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

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance'
  });

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
  sun.shadow.camera.left = -75;
  sun.shadow.camera.right = 75;
  sun.shadow.camera.top = 65;
  sun.shadow.camera.bottom = -65;
  scene.add(sun);

  // SÂN VẬN ĐỘNG
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(230, 170),
    new THREE.MeshStandardMaterial({
      color: 0x183b2b,
      roughness: 1
    })
  );

  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.18;
  ground.receiveShadow = true;
  scene.add(ground);

  const field = new THREE.Mesh(
    new THREE.PlaneGeometry(105, 68),
    new THREE.MeshStandardMaterial({
      color: 0x267b43,
      roughness: 0.95
    })
  );

  field.rotation.x = -Math.PI / 2;
  field.position.y = 0;
  field.receiveShadow = true;
  scene.add(field);

  // CÁC SỌC CỎ
  for (let i = 0; i < 10; i++) {
    const stripe = new THREE.Mesh(
      new THREE.PlaneGeometry(10.5, 68),
      new THREE.MeshStandardMaterial({
        color: i % 2 ? 0x2b8548 : 0x24753f,
        roughness: 1
      })
    );

    stripe.rotation.x = -Math.PI / 2;
    stripe.position.set(-47.25 + i * 10.5, 0.012, 0);
    scene.add(stripe);
  }

  // VẠCH SÂN
  const lineMat = new THREE.MeshBasicMaterial({
    color: 0xf4f5e9
  });

  function line(x1, z1, x2, z2, width = 0.16) {
    const dx = x2 - x1;
    const dz = z2 - z1;
    const len = Math.hypot(dx, dz);

    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(len, width, 0.035),
      lineMat
    );

    mesh.position.set(
      (x1 + x2) / 2,
      0.045,
      (z1 + z2) / 2
    );

    mesh.rotation.y = -Math.atan2(dz, dx);
    scene.add(mesh);
  }

  line(-52.5, -34, 52.5, -34);
  line(-52.5, 34, 52.5, 34);
  line(-52.5, -34, -52.5, 34);
  line(52.5, -34, 52.5, 34);
  line(0, -34, 0, 34);

  const circle = new THREE.Mesh(
    new THREE.RingGeometry(9.05, 9.22, 80),
    lineMat
  );

  circle.rotation.x = -Math.PI / 2;
  circle.position.y = 0.05;
  scene.add(circle);

  const spot = new THREE.Mesh(
    new THREE.CircleGeometry(0.22, 24),
    lineMat
  );

  spot.rotation.x = -Math.PI / 2;
  spot.position.set(0, 0.052, 0);
  scene.add(spot);

  function boxMark(x, z, w, d) {
    const a = new THREE.Mesh(
      new THREE.BoxGeometry(w, 0.035, 0.16),
      lineMat
    );

    a.position.set(x, 0.05, z);
    scene.add(a);

    const b = new THREE.Mesh(
      new THREE.BoxGeometry(0.16, 0.035, d),
      lineMat
    );

    b.position.set(x + (x < 0 ? w / 2 : -w / 2), 0.05, z);
    scene.add(b);

    const c = new THREE.Mesh(
      new THREE.BoxGeometry(w, 0.035, 0.16),
      lineMat
    );

    c.position.set(x, 0.05, z + (z < 0 ? d / 2 : -d / 2));
    scene.add(c);
  }

  boxMark(-43.5, 0, 18, 40.3);
  boxMark(43.5, 0, 18, 40.3);
  boxMark(-49, 0, 6.5, 18.3);
  boxMark(49, 0, 6.5, 18.3);

  // KHUNG THÀNH
  const goalMat = new THREE.MeshStandardMaterial({
    color: 0xf0f2ed,
    metalness: 0.25,
    roughness: 0.45
  });

  function goal(x, direction) {
    const group = new THREE.Group();
    group.position.set(x, 0, 0);
    scene.add(group);

    const width = 7.32;
    const height = 2.45;
    const depth = 3.2;

    for (const z of [-width / 2, width / 2]) {
      const post = new THREE.Mesh(
        new THREE.CylinderGeometry(0.11, 0.11, height, 12),
        goalMat
      );

      post.position.set(0, height / 2, z);
      post.castShadow = true;
      group.add(post);
    }

    const bar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.11, 0.11, width, 12),
      goalMat
    );

    bar.rotation.x = Math.PI / 2;
    bar.position.set(0, height, 0);
    bar.castShadow = true;
    group.add(bar);

    const net = new THREE.Mesh(
      new THREE.BoxGeometry(depth, height, width),
      new THREE.MeshBasicMaterial({
        color: 0xe9f3ed,
        wireframe: true,
        transparent: true,
        opacity: 0.2
      })
    );

    net.position.x = direction * depth / 2;
    net.position.y = height / 2;
    group.add(net);
  }

  goal(-52.5, -1);
  goal(52.5, 1);

  // KHÁN ĐÀI
  const standMat1 = new THREE.MeshStandardMaterial({
    color: 0x334b55,
    roughness: 0.9
  });

  const standMat2 = new THREE.MeshStandardMaterial({
    color: 0x536873,
    roughness: 0.9
  });

  function stand(w, d, x, z, rot = 0) {
    const group = new THREE.Group();

    group.position.set(x, 0, z);
    group.rotation.y = rot;
    scene.add(group);

    for (let i = 0; i < 5; i++) {
      const tier = new THREE.Mesh(
        new THREE.BoxGeometry(w + i * 3, 1.8, d / 5),
        i % 2 ? standMat1 : standMat2
      );

      tier.position.set(0, 1 + i * 1.65, i * 2.2);
      tier.castShadow = true;
      tier.receiveShadow = true;
      group.add(tier);
    }
  }

  stand(112, 18, 0, -48);
  stand(112, 18, 0, 48, Math.PI);
  stand(75, 18, -67, 0, -Math.PI / 2);
  stand(75, 18, 67, 0, Math.PI / 2);

  // KHÁN GIẢ
  const crowdGeo = new THREE.BufferGeometry();
  const crowd = [];

  for (let i = 0; i < 1700; i++) {
    const side = i % 4;
    const t = Math.random();

    let x, z;

    if (side === 0 || side === 1) {
      x = (t - 0.5) * 112;
      z = side === 0 ? -48 : 48;
    } else {
      x = side === 2 ? -67 : 67;
      z = (t - 0.5) * 75;
    }

    crowd.push(x, 2 + Math.random() * 7, z);
  }

  crowdGeo.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(crowd, 3)
  );

  const crowdPoints = new THREE.Points(
    crowdGeo,
    new THREE.PointsMaterial({
      color: 0xd7dedb,
      size: 0.65,
      sizeAttenuation: true
    })
  );

  scene.add(crowdPoints);

  // QUẢ BÓNG
  const ball = new THREE.Mesh(
    new THREE.SphereGeometry(0.48, 24, 16),
    new THREE.MeshStandardMaterial({
      color: 0xf7f7f2,
      roughness: 0.55
    })
  );

  ball.position.set(0, 0.55, 0);
  ball.castShadow = true;
  scene.add(ball);

  // =====================================
  // TẠO 22 CẦU THỦ 3D
  // =====================================

  const players3D = [];

  const skinMaterial = new THREE.MeshStandardMaterial({
    color: 0xd9a078,
    roughness: 0.85
  });

  const hairMaterial = new THREE.MeshStandardMaterial({
    color: 0x29201b,
    roughness: 0.9
  });

  const bootMaterial = new THREE.MeshStandardMaterial({
    color: 0x17191d,
    roughness: 0.65
  });

  function createPlayer(teamColor, number, x, z, isGoalkeeper, direction) {
    const player = new THREE.Group();

    const shirtMaterial = new THREE.MeshStandardMaterial({
      color: isGoalkeeper ? 0xf2c230 : teamColor,
      roughness: 0.72
    });

    const shortsMaterial = new THREE.MeshStandardMaterial({
      color: isGoalkeeper ? 0x252525 : teamColor,
      roughness: 0.8
    });

    // THÂN ÁO
    const torso = new THREE.Mesh(
      new THREE.CylinderGeometry(0.36, 0.43, 0.85, 12),
      shirtMaterial
    );

    torso.position.y = 1.45;
    torso.castShadow = true;
    player.add(torso);

    // CỔ
    const neck = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.13, 0.18, 10),
      skinMaterial
    );

    neck.position.y = 1.94;
    player.add(neck);

    // ĐẦU
    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.25, 16, 12),
      skinMaterial
    );

    head.position.y = 2.22;
    head.scale.set(0.9, 1.1, 0.95);
    head.castShadow = true;
    player.add(head);

    // TÓC
    const hair = new THREE.Mesh(
      new THREE.SphereGeometry(0.255, 14, 10),
      hairMaterial
    );

    hair.position.set(0, 2.34, 0);
    hair.scale.set(0.95, 0.48, 0.98);
    player.add(hair);

    // QUẦN
    const shorts = new THREE.Mesh(
      new THREE.CylinderGeometry(0.37, 0.39, 0.4, 12),
      shortsMaterial
    );

    shorts.position.y = 0.85;
    shorts.castShadow = true;
    player.add(shorts);

    // CHÂN
    for (const side of [-1, 1]) {
      const leg = new THREE.Mesh(
        new THREE.CylinderGeometry(0.105, 0.12, 0.67, 10),
        skinMaterial
      );

      leg.position.set(side * 0.17, 0.39, 0);
      leg.castShadow = true;
      player.add(leg);

      // GIÀY
      const boot = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.13, 0.38),
        bootMaterial
      );

      boot.position.set(side * 0.17, 0.065, 0.1);
      boot.castShadow = true;
      player.add(boot);

      // TAY
      const arm = new THREE.Mesh(
        new THREE.CylinderGeometry(0.09, 0.105, 0.68, 10),
        skinMaterial
      );

      arm.position.set(side * 0.47, 1.45, 0);
      arm.rotation.z = side * -0.12;
      arm.castShadow = true;
      player.add(arm);

      // TAY ÁO
      const sleeve = new THREE.Mesh(
        new THREE.CylinderGeometry(0.13, 0.15, 0.24, 10),
        shirtMaterial
      );

      sleeve.position.set(side * 0.44, 1.7, 0);
      sleeve.rotation.z = side * -0.12;
      player.add(sleeve);
    }

    // SỐ ÁO
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, 128, 128);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 76px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(number), 64, 66);

    const numberTexture = new THREE.CanvasTexture(canvas);
    numberTexture.colorSpace = THREE.SRGBColorSpace;

    const numberMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(0.38, 0.42),
      new THREE.MeshBasicMaterial({
        map: numberTexture,
        transparent: true,
        depthWrite: false
      })
    );

    numberMesh.position.set(0, 1.47, 0.365);
    player.add(numberMesh);

    // HƯỚNG NHÌN CỦA CẦU THỦ
    player.rotation.y = direction;

    player.position.set(x, 0, z);
    scene.add(player);

    players3D.push({
      object: player,
      baseY: 0,
      phase: Math.random() * Math.PI * 2
    });
  }

  // ĐỘI HÌNH 4-3-3
  // Trục X là chiều dài sân, trục Z là chiều ngang sân.

  const homePositions = [
    [-47, 0],   // GK
    [-30, -25],
    [-34, -9],
    [-34, 9],
    [-30, 25],
    [-9, -14],
    [-12, 0],
    [-9, 14],
    [13, -20],
    [17, 0],
    [13, 20]
  ];

  const awayPositions = [
    [47, 0],    // GK
    [30, 25],
    [34, 9],
    [34, -9],
    [30, -25],
    [9, 14],
    [12, 0],
    [9, -14],
    [-13, 20],
    [-17, 0],
    [-13, -20]
  ];

  // ĐỘI NHÀ - ÁO XANH
  homePositions.forEach((pos, index) => {
    createPlayer(
      0x1769d2,
      index === 0 ? 1 : index + 1,
      pos[0],
      pos[1],
      index === 0,
      Math.PI / 2
    );
  });

  // ĐỘI KHÁCH - ÁO ĐỎ
  awayPositions.forEach((pos, index) => {
    createPlayer(
      0xd93636,
      index === 0 ? 1 : index + 1,
      pos[0],
      pos[1],
      index === 0,
      -Math.PI / 2
    );
  });

  // =====================================
  // CAMERA
  // =====================================

  const target = new THREE.Vector3(0, 0, 0);

  function updateCamera() {
    camera.position.set(
      Math.sin(cameraYaw) * cameraDistance,
      cameraHeight,
      Math.cos(cameraYaw) * cameraDistance
    );

    camera.lookAt(target);
  }

  updateCamera();

  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  renderer.domElement.addEventListener('pointerdown', e => {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    renderer.domElement.setPointerCapture(e.pointerId);
  });

  renderer.domElement.addEventListener('pointermove', e => {
    if (!dragging) return;

    cameraYaw -= (e.clientX - lastX) * 0.004;

    cameraHeight = Math.max(
      35,
      Math.min(100, cameraHeight + (e.clientY - lastY) * 0.18)
    );

    lastX = e.clientX;
    lastY = e.clientY;

    updateCamera();
  });

  renderer.domElement.addEventListener('pointerup', () => {
    dragging = false;
  });

  renderer.domElement.addEventListener('pointercancel', () => {
    dragging = false;
  });

  renderer.domElement.addEventListener('wheel', e => {
    cameraDistance = Math.max(
      70,
      Math.min(145, cameraDistance + e.deltaY * 0.06)
    );

    updateCamera();
  }, { passive: true });

  // =====================================
  // KÍCH THƯỚC HIỂN THỊ
  // =====================================

  function resize() {
    const w = mount.clientWidth;
    const h = mount.clientHeight;

    if (!w || !h) return;

    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }

  new ResizeObserver(resize).observe(mount);
  resize();

  // =====================================
  // VÒNG LẶP ANIMATION
  // =====================================

  function animate() {
    requestAnimationFrame(animate);

    ball.rotation.x += 0.003;
    ball.rotation.z += 0.004;

    const time = performance.now() * 0.001;

    // Chuyển động nhịp nhàng khi cầu thủ đứng trên sân.
    players3D.forEach(player => {
      player.object.position.y =
        player.baseY + Math.sin(time * 2 + player.phase) * 0.025;
    });

    renderer.render(scene, camera);
  }

  animate();

} catch (err) {
  console.error('FBM 3D demo error:', err);

  if (errorBox) {
    errorBox.hidden = false;
  }
}
