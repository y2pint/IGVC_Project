from __future__ import annotations

from .auth import API_KEY


def dashboard_html(x_api_key: str | None) -> str:
    """
    Returns the full dashboard HTML.
    If DS_API_KEY is set, the browser will re-use the provided X-API-Key in fetch() calls.
    """
    key_for_browser = x_api_key if API_KEY else ""

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>IGVC Status Monitor</title>

  <!-- Leaflet (GPS map) -->
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>

  <style>
    body {{ font-family: system-ui, sans-serif; margin: 16px; max-width: 1600px; }}
    .grid {{ display: grid; grid-template-columns: 520px 1fr; gap: 12px; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 12px; }}
    button {{ padding: 10px 12px; }}
    pre {{ background: #f7f7f7; padding: 10px; border-radius: 10px; overflow:auto; max-height: 320px; }}
    #map {{ height: 430px; border-radius: 10px; border: 1px solid #ddd; }}
    #navview {{ height: 430px; border-radius: 10px; border: 1px solid #ddd; background: #fff; position: relative; }}
    #navCanvas {{ width: 100%; height: 100%; }}
    .kv {{ display: grid; grid-template-columns: 170px 1fr; gap: 6px 10px; font-size: 14px; }}
    .muted {{ color: #666; font-size: 12px; }}
    .ok {{ color: #136f2d; font-weight: 700; }}
    .bad {{ color: #a11; font-weight: 700; }}
    .warn {{ color: #b36b00; font-weight: 700; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    hr {{ border: none; border-top: 1px solid #eee; margin: 10px 0; }}
    .pill {{ padding: 2px 8px; border-radius: 999px; border: 1px solid #ddd; font-size: 12px; }}
    input {{ padding: 8px; }}
  </style>
</head>

<body>
  <h2>IGVC Status Monitor (GPS + Costmap + Goal Command)</h2>

  <div class="grid">
    <!-- LEFT PANEL -->
    <div class="card">
      <div class="row" style="align-items:center; justify-content: space-between;">
        <div>
          <div><span id="healthBadge" class="muted">Health: unknown</span></div>
          <div class="muted">Refresh: 1 Hz</div>
        </div>
        <div class="row">
          <button onclick="centerOnRobot()">Center GPS</button>
          <button onclick="clearTrail()">Clear GPS trail</button>
          <button onclick="refresh()">Refresh</button>
        </div>
      </div>

      <hr/>

      <h3 style="margin: 6px 0;">GPS</h3>
      <div class="kv">
        <div>Fix</div><div id="gpsLine" class="muted">—</div>
        <div>Satellites</div><div id="satLine" class="muted">—</div>
        <div>Cov (m)</div><div id="covLine" class="muted">—</div>
        <div>GPS validity</div><div id="gpsValidLine" class="muted">—</div>
        <div>Fix age (s)</div><div id="ageLine" class="muted">—</div>
      </div>

      <hr/>

      <h3 style="margin: 6px 0;">TF Health</h3>
      <pre id="tfPanel" class="mono"></pre>

      <h3 style="margin: 6px 0;">Freshness (Age / Hz)</h3>
      <pre id="freshness" class="mono"></pre>

      <hr/>

      <h3 style="margin: 6px 0;">Goal Pose (Read-only)</h3>
      <div class="muted" style="margin-bottom:8px;">
        Click on the costmap view to set X,Y. Drag to set yaw. This will only generate a command string.
      </div>
      <div class="kv">
        <div>Goal (map)</div><div id="goalLine" class="mono">—</div>
        <div>Yaw (deg)</div>
        <div>
          <input id="yawDeg" type="number" value="0" style="width:120px;" onchange="updateGoalYawFromInput()"/>
          <span class="muted">manual override</span>
        </div>
      </div>

      <div style="margin-top:8px;">
        <div class="row" style="align-items:center; justify-content: space-between;">
          <div class="muted">Command:</div>
          <div class="row" style="gap:8px;">
            <button onclick="copyGoalCmd()">Copy</button>
            <span id="copyHint" class="muted"></span>
          </div>
        </div>
        <pre id="goalCmd" class="mono"></pre>
      </div>
      
      <hr/>

      <h3 style="margin: 6px 0;">Health</h3>
      <pre id="health"></pre>

      <h3 style="margin: 6px 0;">Full Status</h3>
      <pre id="status"></pre>
    </div>

    <!-- RIGHT PANEL -->
    <div class="card">
      <div class="row" style="align-items:flex-start;">
        <div style="flex:1;">
          <h3 style="margin-top: 0;">GPS Map (OSM)</h3>
          <div class="muted" style="margin-bottom: 8px;">
            Outdoor validation view (lat/lon). Requires internet for map tiles.
          </div>
          <div id="map"></div>
        </div>
        <div style="flex:1;">
          <h3 style="margin-top: 0;">Nav2 View (Costmap in meters)</h3>
          <div class="row" style="align-items:center; margin-bottom:8px;">
            <span class="pill">Canvas units: meters</span>
            <span class="pill" id="cmMode">costmap: local</span>
            <button onclick="toggleCostmap()">Toggle local/global</button>
            <button onclick="fitCostmap()">Fit</button>
            <button onclick="clearGoal()">Clear goal</button>
          </div>
          <div id="navview">
            <canvas id="navCanvas"></canvas>
          </div>
          <div class="muted" style="margin-top:8px;">
            Robot pose uses /odometry/filtered (x,y,yaw). Costmap uses OccupancyGrid origin/resolution.
          </div>
        </div>
      </div>
    </div>
  </div>

<script>
const DS_API_KEY = {repr(key_for_browser)};
const MAX_TRAIL = 300;

function fetchHeaders() {{
  if (DS_API_KEY && DS_API_KEY.length > 0) {{
    return {{ 'X-API-Key': DS_API_KEY }};
  }}
  return {{}};
}}

function safeNum(x) {{
  return (typeof x === 'number' && isFinite(x)) ? x : null;
}}

function badge(text, cls) {{
  return `<span class="${{cls}}">${{text}}</span>`;
}}

async function copyGoalCmd() {{
  const pre = document.getElementById("goalCmd");
  const hint = document.getElementById("copyHint");
  if (!pre) return;

  const text = (pre.textContent || "").trim();
  if (!text) {{
    if (hint) hint.textContent = "No command to copy.";
    return;
  }}

  try {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      await navigator.clipboard.writeText(text);
    }} else {{
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }}

    if (hint) {{
      hint.textContent = "Copied.";
      setTimeout(() => {{ hint.textContent = ""; }}, 1200);
    }}
  }} catch (e) {{
    if (hint) hint.textContent = "Copy failed.";
  }}
}}


// ---------------- GPS Leaflet Map ----------------
let map = null;
let robotMarker = null;
let trailLine = null;
let accuracyCircle = null;
let trail = [];
let lastLatLon = null;

function initGpsMap() {{
  map = L.map('map').setView([36.162, -85.501], 17);

  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 20,
    attribution: '&copy; OpenStreetMap contributors'
  }}).addTo(map);

  robotMarker = L.circleMarker([36.162, -85.501], {{
    radius: 7,
    weight: 2,
    fillOpacity: 0.8
  }}).addTo(map);

  trailLine = L.polyline([], {{ weight: 3 }}).addTo(map);

  accuracyCircle = L.circle([36.162, -85.501], {{
    radius: 3,
    weight: 1,
    fillOpacity: 0.08
  }}).addTo(map);
}}

function clearTrail() {{
  trail = [];
  if (trailLine) trailLine.setLatLngs(trail);
}}

function centerOnRobot() {{
  if (!map) return;
  if (lastLatLon) map.setView(lastLatLon, Math.max(map.getZoom(), 18));
}}

function updateGpsMapFromStatus(j) {{
  const gps = j.gps || {{}};
  const lat = safeNum(gps.lat);
  const lon = safeNum(gps.lon);
  if (lat === null || lon === null) return;

  lastLatLon = [lat, lon];

  const last = trail.length ? trail[trail.length - 1] : null;
  const eps = 1e-7;
  if (!last || (Math.abs(last[0]-lat) > eps || Math.abs(last[1]-lon) > eps)) {{
    trail.push([lat, lon]);
    if (trail.length > MAX_TRAIL) trail.shift();
  }}

  robotMarker.setLatLng([lat, lon]);
  trailLine.setLatLngs(trail);

  const cov_xx = safeNum(gps.cov_xx);
  const cov_yy = safeNum(gps.cov_yy);
  let sigma_m = 3.0;
  if (cov_xx !== null && cov_yy !== null && cov_xx > 0 && cov_yy > 0) {{
    sigma_m = Math.sqrt(0.5 * (cov_xx + cov_yy));
    sigma_m = Math.min(Math.max(sigma_m, 0.5), 50.0);
  }}
  accuracyCircle.setLatLng([lat, lon]);
  accuracyCircle.setRadius(sigma_m);

  if (trail.length === 1) {{
    map.setView([lat, lon], 18);
  }}
}}

// ---------------- Costmap Canvas (meters) ----------------
let cmWhich = "local";
let cmData = null;
let statusData = null;

let view = {{
  x_min: -5, x_max: 5,
  y_min: -5, y_max: 5
}};

let goal = null;
let dragStart = null;

const navCanvas = document.getElementById("navCanvas");
const navParent = document.getElementById("navview");
const ctx = navCanvas.getContext("2d");

function resizeCanvas() {{
  navCanvas.width = navParent.clientWidth;
  navCanvas.height = navParent.clientHeight;
}}

window.addEventListener("resize", () => {{
  resizeCanvas();
  drawNavView();
}});

function toggleCostmap() {{
  cmWhich = (cmWhich === "local") ? "global" : "local";
  document.getElementById("cmMode").textContent = "costmap: " + cmWhich;
  fetchCostmap();
}}

function fitCostmap() {{
  if (!cmData || !cmData.present || !cmData.resolution || !cmData.width || !cmData.height) return;
  const ox = cmData.origin_x;
  const oy = cmData.origin_y;
  const w_m = cmData.width * cmData.resolution;
  const h_m = cmData.height * cmData.resolution;
  const m = 0.10;
  view.x_min = ox - w_m*m;
  view.x_max = ox + w_m*(1+m);
  view.y_min = oy - h_m*m;
  view.y_max = oy + h_m*(1+m);
  drawNavView();
}}

function clearGoal() {{
  goal = null;
  dragStart = null;
  document.getElementById("goalLine").textContent = "—";
  document.getElementById("goalCmd").textContent = "";
  drawNavView();
}}

function worldToCanvas(x, y) {{
  const W = navCanvas.width, H = navCanvas.height;
  const u = (x - view.x_min) / (view.x_max - view.x_min);
  const v = (y - view.y_min) / (view.y_max - view.y_min);
  const cx = u * W;
  const cy = (1 - v) * H;
  return [cx, cy];
}}

function canvasToWorld(cx, cy) {{
  const W = navCanvas.width, H = navCanvas.height;
  const u = cx / W;
  const v = 1 - (cy / H);
  const x = view.x_min + u * (view.x_max - view.x_min);
  const y = view.y_min + v * (view.y_max - view.y_min);
  return [x, y];
}}

function drawCostmap() {{
  if (!cmData || !cmData.present || !cmData.gray || cmData.gray.length === 0) {{
    ctx.clearRect(0,0,navCanvas.width, navCanvas.height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0,0,navCanvas.width, navCanvas.height);
    ctx.fillStyle = "#666";
    ctx.fillText("Costmap not available", 20, 30);
    return;
  }}

  const rw = cmData.render_w;
  const rh = cmData.render_h;
  const gray = cmData.gray;

  const img = ctx.createImageData(rw, rh);
  for (let i=0; i<rw*rh; i++) {{
    const g = gray[i];
    img.data[i*4+0] = g;
    img.data[i*4+1] = g;
    img.data[i*4+2] = g;
    img.data[i*4+3] = 255;
  }}

  const off = document.createElement("canvas");
  off.width = rw;
  off.height = rh;
  const octx = off.getContext("2d");
  octx.putImageData(img, 0, 0);

  const ox = cmData.origin_x;
  const oy = cmData.origin_y;
  const w_m = cmData.width * cmData.resolution;
  const h_m = cmData.height * cmData.resolution;

  const [x0,y0] = worldToCanvas(ox, oy);
  const [x1,y1] = worldToCanvas(ox + w_m, oy + h_m);

  const left = Math.min(x0,x1);
  const top = Math.min(y0,y1);
  const right = Math.max(x0,x1);
  const bottom = Math.max(y0,y1);

  ctx.clearRect(0,0,navCanvas.width, navCanvas.height);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(off, left, top, (right-left), (bottom-top));

  ctx.save();
  ctx.strokeStyle = "rgba(0,0,0,0.12)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.rect(left, top, (right-left), (bottom-top));
  ctx.stroke();
  ctx.restore();
}}

function drawRobotPose() {{
  if (!statusData || !statusData.localization) return;

  const loc = statusData.localization;
  const x = safeNum(loc.x);
  const y = safeNum(loc.y);
  const yaw = safeNum(loc.yaw_rad);
  if (x === null || y === null || yaw === null) return;

  const [cx, cy] = worldToCanvas(x, y);

  // Robot footprint
  const footprint_radius_m = 0.40;
  const [cx_r, cy_r] = worldToCanvas(x + footprint_radius_m, y);
  const r_px = Math.max(6, Math.abs(cx_r - cx));

  ctx.save();
  ctx.strokeStyle = "rgba(30, 90, 200, 0.55)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r_px, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();

  // Robot center
  ctx.save();
  ctx.fillStyle = "rgba(30, 90, 200, 0.95)";
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Heading
  const len = 18;
  const hx = cx + len * Math.cos(yaw);
  const hy = cy - len * Math.sin(yaw);

  ctx.save();
  ctx.strokeStyle = "rgba(30, 90, 200, 0.95)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(hx, hy);
  ctx.stroke();
  ctx.restore();

  // Pose label (THIS WAS THE BUG)
  ctx.save();
  ctx.font = "12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  ctx.fillStyle = "rgba(30, 90, 200, 0.95)";
  ctx.fillText(`(${{x.toFixed(2)}}, ${{y.toFixed(2)}})`, cx + 8, cy - 8);
  ctx.restore();
}}


function drawGoalPose() {{
  if (!goal) return;
  const [cx, cy] = worldToCanvas(goal.x, goal.y);

  ctx.save();
  ctx.fillStyle = "rgba(200, 40, 40, 0.95)";
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI*2);
  ctx.fill();

  const len = 18;
  const hx = cx + len * Math.cos(goal.yaw);
  const hy = cy - len * Math.sin(goal.yaw);
  ctx.strokeStyle = "rgba(200, 40, 40, 0.95)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(hx, hy);
  ctx.stroke();
  ctx.restore();
}}

function drawNavView() {{
  resizeCanvas();
  drawCostmap();
  drawRobotPose();
  drawGoalPose();

   // Debug overlay (top-left)
  ctx.save();
  ctx.font = "12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  ctx.fillStyle = "rgba(0,0,0,0.75)";
  const loc = (statusData && statusData.localization) ? statusData.localization : null;
  const cmf = (cmData && cmData.frame_id) ? cmData.frame_id : "—";
  const lf  = (loc && loc.frame_id) ? loc.frame_id : "—";
  const x = (loc && typeof loc.x === "number") ? loc.x.toFixed(2) : "—";
  const y = (loc && typeof loc.y === "number") ? loc.y.toFixed(2) : "—";
  ctx.fillText(`cm_frame=${{cmf}}  loc_frame=${{lf}}  loc=(${{x}},${{y}})`, 10, 18);
  ctx.restore();
  
}}

function setGoal(x, y, yaw) {{
  goal = {{x, y, yaw}};
  document.getElementById("goalLine").textContent =
    `x=${{x.toFixed(2)}}, y=${{y.toFixed(2)}}, yaw=${{(yaw*180/Math.PI).toFixed(1)}} deg`;
  document.getElementById("yawDeg").value = (yaw*180/Math.PI).toFixed(1);

  const qz = Math.sin(yaw/2.0);
  const qw = Math.cos(yaw/2.0);

  const cmd =
`ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{
  pose: {{
    header: {{ frame_id: map }},
    pose: {{
      position: {{ x: ${{x.toFixed(3)}}, y: ${{y.toFixed(3)}}, z: 0.0 }},
      orientation: {{ x: 0.0, y: 0.0, z: ${{qz.toFixed(6)}}, w: ${{qw.toFixed(6)}} }}
    }}
  }}
}}"`;

  document.getElementById("goalCmd").textContent = cmd;
  drawNavView();
}}

function updateGoalYawFromInput() {{
  if (!goal) return;
  const deg = parseFloat(document.getElementById("yawDeg").value);
  if (!isFinite(deg)) return;
  goal.yaw = deg * Math.PI / 180.0;
  setGoal(goal.x, goal.y, goal.yaw);
}}

navCanvas.addEventListener("mousedown", (ev) => {{
  const rect = navCanvas.getBoundingClientRect();
  const cx = ev.clientX - rect.left;
  const cy = ev.clientY - rect.top;
  const [x, y] = canvasToWorld(cx, cy);

  const yaw = (goal && typeof goal.yaw === "number") ? goal.yaw : 0.0;
  setGoal(x, y, yaw);
  dragStart = {{x, y, cx, cy}};
}});

navCanvas.addEventListener("mousemove", (ev) => {{
  if (!dragStart || !goal) return;
  const rect = navCanvas.getBoundingClientRect();
  const cx = ev.clientX - rect.left;
  const cy = ev.clientY - rect.top;
  const [x2, y2] = canvasToWorld(cx, cy);

  const dx = x2 - goal.x;
  const dy = y2 - goal.y;
  const dist = Math.sqrt(dx*dx + dy*dy);
  if (dist < 0.2) return;

  const yaw = Math.atan2(dy, dx);
  setGoal(goal.x, goal.y, yaw);
}});

navCanvas.addEventListener("mouseup", () => {{ dragStart = null; }});
navCanvas.addEventListener("mouseleave", () => {{ dragStart = null; }});

// ---------------- Fetch /status and /costmap ----------------
async function fetchCostmap() {{
  try {{
    const r = await fetch(`/costmap/${{cmWhich}}`, {{ cache: 'no-store', headers: fetchHeaders() }});
    if (!r.ok) throw new Error(`HTTP ${{r.status}}`);
    cmData = await r.json();
    if (cmData && cmData.present) {{
      fitCostmap();
    }}
    drawNavView();
  }} catch(e) {{
    if (!cmData) cmData = null;
    drawNavView();
  }}
}}

function updateLeftPanel(j) {{
  const gps = j.gps || {{}};
  const sats = j.gps_sats || {{}};
  const validity = j.gps_validity || {{}};

  const lat = safeNum(gps.lat);
  const lon = safeNum(gps.lon);

  document.getElementById('gpsLine').textContent =
    (lat !== null && lon !== null) ? `${{lat.toFixed(7)}}, ${{lon.toFixed(7)}}` : '—';

  const sv = (sats && sats.satellites_visible !== null && sats.satellites_visible !== undefined)
    ? sats.satellites_visible : null;
  document.getElementById('satLine').textContent = (sv !== null) ? String(sv) : '—';

  const cov_xx = safeNum(gps.cov_xx);
  const cov_yy = safeNum(gps.cov_yy);
  if (cov_xx !== null && cov_yy !== null && cov_xx > 0 && cov_yy > 0) {{
    const sx = Math.sqrt(cov_xx);
    const sy = Math.sqrt(cov_yy);
    document.getElementById('covLine').textContent = `σx=${{sx.toFixed(2)}} m, σy=${{sy.toFixed(2)}} m`;
  }} else {{
    document.getElementById('covLine').textContent = '—';
  }}

  const now = (typeof j.time_unix === 'number') ? j.time_unix : (Date.now()/1000.0);
  const age = (typeof gps.stamp_unix === 'number') ? (now - gps.stamp_unix) : null;
  document.getElementById('ageLine').textContent = (age !== null) ? age.toFixed(2) : '—';

  let cls = validity.cls || 'unknown';
  let reason = validity.reason || 'unknown';
  let badgeCls = 'muted';
  if (cls === 'good') badgeCls = 'ok';
  else if (cls === 'degraded') badgeCls = 'warn';
  else if (cls === 'poor' || cls === 'no_fix') badgeCls = 'bad';
  const extra = (validity.rms_cov_m !== null && validity.rms_cov_m !== undefined)
    ? ` | rms_cov=${{Number(validity.rms_cov_m).toFixed(2)}}m` : '';
  document.getElementById('gpsValidLine').innerHTML =
    `${{badge(cls, badgeCls)}} <span class="muted">(${{reason}})</span>${{extra}}`;

  const healthOk = j.health && j.health.ok === true;
  const badgeEl = document.getElementById('healthBadge');
  badgeEl.textContent = `Health: ${{healthOk ? 'OK' : 'CHECK'}}`;
  badgeEl.className = healthOk ? 'ok' : 'bad';

  const tf = j.tf || {{}};
  const lines = [];
  function tfLine(ok, name) {{
    return `${{ok ? badge('OK','ok') : badge('MISSING','bad')}}  ${{name}}`;
  }}
  lines.push(tfLine(tf.map_to_odom, 'map→odom'));
  lines.push(tfLine(tf.odom_to_base, 'odom→base_link'));
  lines.push(tfLine(tf.map_to_base, 'map→base_link (optional)'));
  document.getElementById('tfPanel').innerHTML = lines.join('\\n');

  const f = j.topic_freshness || {{}};
  const keys = Object.keys(f);
  keys.sort();
  const flines = keys.map(k => {{
    const o = f[k];
    const p = o.present ? badge('P','ok') : badge('A','bad');
    const a = (o.age_sec === null || o.age_sec === undefined) ? '—' : o.age_sec.toFixed(2);
    const hz = (o.ema_hz === null || o.ema_hz === undefined) ? '—' : o.ema_hz.toFixed(1);
    return `${{p}}  ${{k.padEnd(14)}}  age=${{a}}s  hz=${{hz}}`;
  }});
  document.getElementById('freshness').textContent = flines.join('\\n');
}}

async function refresh() {{
  try {{
    const r = await fetch('/status', {{ cache: 'no-store', headers: fetchHeaders() }});
    if (!r.ok) throw new Error(`HTTP ${{r.status}}`);
    const j = await r.json();

    statusData = j;

    document.getElementById('health').textContent = JSON.stringify(j.health, null, 2);
    document.getElementById('status').textContent = JSON.stringify(j, null, 2);

    updateLeftPanel(j);
    updateGpsMapFromStatus(j);
    drawNavView();
  }} catch (e) {{
    document.getElementById('health').textContent =
      JSON.stringify({{ ok: false, error: String(e) }}, null, 2);
  }}
}}

initGpsMap();
resizeCanvas();
fetchCostmap();
refresh();
setInterval(refresh, 1000);
setInterval(fetchCostmap, 1000);
</script>

</body>
</html>
"""
