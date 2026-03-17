from __future__ import annotations

from .auth import API_KEY


def dashboard_html(x_api_key: str | None) -> str:
    key_for_browser = x_api_key if API_KEY else ""

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>IGVC Status Monitor</title>

  <link rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>

  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 12px;
           display: flex; flex-direction: column; gap: 10px;
           background: #f5f5f5; min-height: 100vh; }}

    /* ── Top bar ── */
    #topbar {{
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      background: #fff; border: 1px solid #ddd; border-radius: 10px;
      padding: 8px 14px; flex-shrink: 0;
    }}
    #topbar h2 {{ margin: 0; font-size: 15px; font-weight: 700; white-space: nowrap; }}
    #topbar .sep {{ width: 1px; height: 24px; background: #e0e0e0; flex-shrink: 0; }}
    #topbar .status-group {{ display: flex; gap: 14px; flex-wrap: wrap; align-items: center; font-size: 13px; }}
    #topbar .btn-group {{ display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }}
    #topbar button {{ padding: 5px 10px; font-size: 13px; border-radius: 6px; border: 1px solid #ccc; background: #fafafa; cursor: pointer; }}
    #topbar button:hover {{ background: #eef; }}

    /* ── Main grid ── */
    #main {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: auto auto;
      gap: 10px;
      flex: 1;
    }}

    .panel {{
      background: #fff; border: 1px solid #ddd; border-radius: 10px;
      padding: 10px; display: flex; flex-direction: column; min-height: 0;
    }}
    .panel-header {{
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      margin-bottom: 8px; flex-shrink: 0;
    }}
    .panel-header h3 {{ margin: 0; font-size: 14px; font-weight: 700; }}
    .panel-header button {{ padding: 4px 9px; font-size: 12px; border-radius: 6px; border: 1px solid #ccc; background: #fafafa; cursor: pointer; }}
    .panel-header button:hover {{ background: #eef; }}

    /* GPS map panel (top-left) */
    #map-wrapper {{
      flex: 1; min-height: 320px; position: relative;
      border-radius: 8px; border: 1px solid #ddd; overflow: hidden;
    }}
    #map {{ width: 100%; height: 100%; border: none; border-radius: 0;
      transform-origin: center center; transition: transform 0.1s ease; }}
    #dzoom-badge {{
      position: absolute; bottom: 6px; right: 6px; z-index: 1000;
      background: rgba(255,255,255,0.88); border: 1px solid #ccc;
      border-radius: 6px; padding: 2px 7px; font-size: 11px;
      font-family: ui-monospace, monospace; pointer-events: none;
    }}

    /* Nav2 costmap panel (top-right) */
    #navview {{ flex: 1; border-radius: 8px; border: 1px solid #ddd;
               background: #fff; position: relative; min-height: 320px; overflow: hidden; }}
    #navCanvas {{ width: 100%; height: 100%; display: block; }}

    /* Navigation status panel (bottom-left) */
    #navStatusPanel {{ grid-column: 1; }}
    .nav-grid {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
    }}
    .nav-section {{ }}
    .nav-section h4 {{ margin: 0 0 6px; font-size: 13px; font-weight: 700; color: #444; }}

    /* BT events table */
    #btEventsTable {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    #btEventsTable th {{
      text-align: left; padding: 3px 6px; background: #f0f0f0;
      border-bottom: 1px solid #ddd; font-size: 11px;
    }}
    #btEventsTable td {{ padding: 2px 6px; border-bottom: 1px solid #f0f0f0; }}
    #btEventsTable tr:hover {{ background: #fafafa; }}
    .bt-running  {{ color: #1565c0; font-weight: 700; }}
    .bt-success  {{ color: #2e7d32; font-weight: 700; }}
    .bt-failure  {{ color: #c62828; font-weight: 700; }}
    .bt-idle     {{ color: #888; }}

    /* Diagnostics panel (bottom-right) */
    #diagPanel {{ grid-column: 2; }}

    /* ── Shared utilities ── */
    .row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .kv {{ display: grid; grid-template-columns: 160px 1fr; gap: 3px 8px; font-size: 13px; }}
    .muted {{ color: #666; font-size: 12px; }}
    .ok   {{ color: #136f2d; font-weight: 700; }}
    .bad  {{ color: #a11;    font-weight: 700; }}
    .warn {{ color: #b36b00; font-weight: 700; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    pre {{ background: #f7f7f7; padding: 8px; border-radius: 8px;
           overflow: auto; max-height: 180px; margin: 4px 0 0; font-size: 12px; }}
    .pill {{ padding: 2px 8px; border-radius: 999px; border: 1px solid #ddd; font-size: 12px; }}
    .recovery-pill {{
      padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 700;
      background: #ffcdd2; color: #b71c1c; border: 1px solid #ef9a9a;
      animation: pulse 0.8s infinite;
    }}
    @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.5; }} }}
    input {{ padding: 6px; font-size: 13px; border: 1px solid #ccc; border-radius: 6px; }}
    hr {{ border: none; border-top: 1px solid #eee; margin: 6px 0; }}
    details summary {{ cursor: pointer; font-size: 13px; font-weight: 600; margin: 6px 0 4px; }}
    details[open] summary {{ margin-bottom: 6px; }}

    /* speed bar */
    .speed-bar-wrap {{ background: #eee; border-radius: 4px; height: 10px; overflow: hidden; margin-top: 3px; }}
    .speed-bar {{ height: 100%; border-radius: 4px; transition: width 0.2s, background 0.2s; }}
  </style>
</head>

<body>

  <!-- ══ TOP BAR ══════════════════════════════════════════════════════════ -->
  <div id="topbar">
    <h2>IGVC Status Monitor</h2>
    <div class="sep"></div>

    <div class="status-group">
      <span id="healthBadge" class="muted">Health: —</span>
      <span class="muted">|</span>
      <span class="muted">Fix:</span><span id="gpsLine" class="mono muted">—</span>
      <span class="muted">|</span>
      <span class="muted">Sats:</span><span id="satLine" class="mono muted">—</span>
      <span class="muted">|</span>
      <span class="muted">Cov:</span><span id="covLine" class="mono muted">—</span>
      <span class="muted">|</span>
      <span class="muted">Age:</span><span id="ageLine" class="mono muted">—</span>
      <span class="muted">|</span>
      <span id="gpsValidLine" class="muted">—</span>
      <span class="muted">|</span>
      <!-- NEW: speed + BT status in topbar -->
      <span class="muted">vx:</span><span id="topVx" class="mono muted">—</span>
      <span class="muted">|</span>
      <span id="topBTStatus" class="muted">BT: —</span>
      <span class="muted">|</span>
      <span id="topMavros" class="muted">APM: —</span>
    </div>

    <div class="btn-group">
      <button onclick="centerOnRobot()">⊕ Center GPS</button>
      <button onclick="clearTrail()">✕ Clear Trail</button>
      <button onclick="_anchor=null" title="Re-lock projection anchor">↺ Reset Anchor</button>
      <div class="sep"></div>
      <button id="btnMissionStart" onclick="missionCommand('start')"
              title="Reset waypoints to index 0 and enable navigation">▶ Start</button>
      <button id="btnMissionStop" onclick="missionCommand('stop')"
              title="Disable navigation">⏹ Stop</button>
      <button onclick="missionCommand('next')" title="Advance to next waypoint">⏭ Next WP</button>
      <button onclick="missionCommand('cancel')" title="One-shot cancel Nav2 goal">✕ Cancel Goal</button>
      <button onclick="missionCommand('reset')" title="Re-lock GPS origin">⚓ Reset Origin</button>
      <span id="navEnabledPill" class="pill" style="background:#e0e0e0;color:#555">nav: ?</span>
      <span id="missionCmdHint" class="muted"></span>
      <div class="sep"></div>
      <span class="pill" id="cmMode">costmap: local</span>
      <button onclick="toggleCostmap()">⇄ Toggle Costmap</button>
      <button onclick="fitCostmap()">⤢ Fit</button>
      <button onclick="clearGoal()">✕ Clear Goal</button>
      <div class="sep"></div>
      <button onclick="refresh()">↺ Refresh</button>
    </div>
  </div>

  <!-- ══ MAIN GRID ════════════════════════════════════════════════════════ -->
  <div id="main">

    <!-- ── TOP-LEFT: GPS Map ── -->
    <div class="panel">
      <div class="panel-header">
        <h3>GPS Map (OSM)</h3>
        <span class="muted" style="margin-left:4px;">lat/lon</span>
        <button onclick="map.zoomIn()"  style="font-size:15px;line-height:1;padding:2px 8px;">+</button>
        <button onclick="map.zoomOut()" style="font-size:15px;line-height:1;padding:2px 8px;">−</button>
        <span class="muted" style="margin-left:6px;font-size:11px;">Digital:</span>
        <button onclick="digitalZoom(1)"     style="font-size:15px;line-height:1;padding:2px 8px;">+</button>
        <button onclick="digitalZoom(-1)"    style="font-size:15px;line-height:1;padding:2px 8px;">−</button>
        <button onclick="digitalZoomReset()" style="font-size:11px;padding:3px 7px;">1×</button>
        <details style="margin-left:auto;">
          <summary>Diagnostics ▾</summary>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px;">
            <div>
              <div style="font-size:12px;font-weight:600;margin-bottom:4px;">TF Health</div>
              <pre id="tfPanel" class="mono" style="max-height:100px;"></pre>
            </div>
            <div>
              <div style="font-size:12px;font-weight:600;margin-bottom:4px;">Freshness (Age / Hz)</div>
              <pre id="freshness" class="mono" style="max-height:100px;"></pre>
            </div>
          </div>
          <div style="margin-top:6px;">
            <div style="font-size:12px;font-weight:600;margin-bottom:4px;">Health JSON</div>
            <pre id="health" style="max-height:100px;"></pre>
          </div>
        </details>
      </div>
      <div id="map-wrapper">
        <div id="map"></div>
        <div id="dzoom-badge">1.0×</div>
      </div>
    </div>

    <!-- ── TOP-RIGHT: Nav2 Costmap ── -->
    <div class="panel">
      <div class="panel-header">
        <h3>Nav2 View</h3>
        <span class="pill">meters</span>
        <span class="muted" style="margin-left:8px;">Goal:</span>
        <span id="goalLine" class="mono muted">—</span>
        <span class="muted">Yaw:</span>
        <input id="yawDeg" type="number" value="0" style="width:80px;"
               onchange="updateGoalYawFromInput()"/>
        <button onclick="copyGoalCmd()" style="margin-left:4px;">⎘ Copy cmd</button>
        <span id="copyHint" class="muted"></span>
      </div>
      <pre id="goalCmd" class="mono"
           style="max-height:0;padding:0;margin:0;overflow:hidden;border:none;background:none;"></pre>
      <div id="navview">
        <canvas id="navCanvas"></canvas>
      </div>
      <div class="muted" style="margin-top:6px;font-size:11px;">
        Click to set goal · drag to set yaw · costmap: OccupancyGrid
      </div>
    </div>

    <!-- ── BOTTOM-LEFT: Navigation Status ── -->
    <div class="panel" id="navStatusPanel">
      <div class="panel-header">
        <h3>Navigation Status</h3>
        <span id="recoveryPill" style="display:none;" class="recovery-pill">⚠ RECOVERY</span>
        <span id="recoveryCount" class="muted" style="margin-left:6px;"></span>
      </div>

      <div class="nav-grid">

        <!-- Left column: speed + MPPI + MAVROS -->
        <div class="nav-section">
          <h4>Velocity (cmd_vel)</h4>
          <div class="kv">
            <span class="muted">Linear vx</span>
            <span id="cvVx" class="mono">—</span>
            <span></span>
            <div class="speed-bar-wrap" style="width:140px;">
              <div id="cvVxBar" class="speed-bar" style="width:0%;background:#1565c0;"></div>
            </div>
            <span class="muted">Angular wz</span>
            <span id="cvWz" class="mono">—</span>
          </div>

          <hr/>
          <h4>ArduPilot (MAVROS)</h4>
          <div class="kv">
            <span class="muted">Connected</span>  <span id="mavConnected">—</span>
            <span class="muted">Armed</span>       <span id="mavArmed">—</span>
            <span class="muted">Mode</span>        <span id="mavMode" class="mono">—</span>
            <span class="muted">Battery</span>     <span id="mavBattery" class="mono">—</span>
          </div>

          <hr/>
          <h4>BT Node Status</h4>
          <div class="kv">
            <span class="muted">FollowPath</span>
            <span id="btFollowPath" class="mono">—</span>
            <span class="muted">ComputePath</span>
            <span id="btComputePath" class="mono">—</span>
            <span class="muted">Nav active</span>
            <span id="navActive" class="mono">—</span>
          </div>
        </div>

        <!-- Right column: BT event log -->
        <div class="nav-section">
          <h4>BT Event Log <span class="muted" style="font-weight:400;">(last 20)</span></h4>
          <div style="overflow-y:auto;max-height:240px;">
            <table id="btEventsTable">
              <thead>
                <tr>
                  <th>Node</th>
                  <th>→ Status</th>
                  <th>Age</th>
                </tr>
              </thead>
              <tbody id="btEventsTbody">
                <tr><td colspan="3" class="muted">No events yet</td></tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>

    <!-- ── BOTTOM-RIGHT: Diagnostics ── -->
    <div class="panel" id="diagPanel">
      <div class="panel-header">
        <h3>Diagnostics</h3>
      </div>
      <div class="nav-grid">
        <div>
          <h4 style="margin:0 0 4px;font-size:13px;font-weight:700;color:#444;">VESC Left</h4>
          <div class="kv" id="vescKv">
            <span class="muted">Voltage</span>    <span id="vescVolt" class="mono">—</span>
            <span class="muted">Current (in)</span><span id="vescCurrIn" class="mono">—</span>
            <span class="muted">Current (mot)</span><span id="vescCurrMot" class="mono">—</span>
            <span class="muted">Duty</span>        <span id="vescDuty" class="mono">—</span>
            <span class="muted">ERPM</span>        <span id="vescErpm" class="mono">—</span>
            <span class="muted">Temp FET</span>    <span id="vescTempFet" class="mono">—</span>
            <span class="muted">Temp Motor</span>  <span id="vescTempMot" class="mono">—</span>
            <span class="muted">Fault</span>       <span id="vescFault" class="mono">—</span>
          </div>
        </div>
        <div>
          <h4 style="margin:0 0 4px;font-size:13px;font-weight:700;color:#444;">Localization</h4>
          <div class="kv">
            <span class="muted">x</span>         <span id="locX" class="mono">—</span>
            <span class="muted">y</span>         <span id="locY" class="mono">—</span>
            <span class="muted">yaw</span>       <span id="locYaw" class="mono">—</span>
            <span class="muted">cov_xx</span>    <span id="locCovXX" class="mono">—</span>
            <span class="muted">cov_yy</span>    <span id="locCovYY" class="mono">—</span>
            <span class="muted">frame</span>     <span id="locFrame" class="mono">—</span>
          </div>
          <hr/>
          <h4 style="margin:4px 0;font-size:13px;font-weight:700;color:#444;">Stop Flag</h4>
          <span id="stopFlagBadge" class="muted">—</span>
        </div>
      </div>
    </div>

  </div><!-- end #main -->

  <pre id="status" style="display:none;"></pre>

<script>
const DS_API_KEY = {repr(key_for_browser)};
const MAX_TRAIL  = 300;

function fetchHeaders() {{
  return DS_API_KEY && DS_API_KEY.length > 0
    ? {{'X-API-Key': DS_API_KEY}}
    : {{}};
}}

// ── Mission commands ──────────────────────────────────────────────────────────
async function missionCommand(cmd) {{
  const hint = document.getElementById('missionCmdHint');
  if (hint) hint.textContent = `Sending ${{cmd}}…`;
  try {{
    const r = await fetch(`/mission/command/${{cmd}}`, {{
      method: 'POST', cache: 'no-store', headers: fetchHeaders(),
    }});
    const j = await r.json();
    const ok  = j.success === true;
    const txt = j.message || j.detail || (ok ? 'OK' : 'Failed');
    if (hint) {{
      hint.textContent  = ok ? `✓ ${{txt}}` : `✗ ${{txt}}`;
      hint.style.color  = ok ? '#136f2d' : '#a11';
      setTimeout(() => {{ hint.textContent = ''; hint.style.color = ''; }}, 4000);
    }}
  }} catch(e) {{
    if (hint) {{
      hint.textContent = `✗ ${{e}}`; hint.style.color = '#a11';
      setTimeout(() => {{ hint.textContent = ''; hint.style.color = ''; }}, 4000);
    }}
  }}
}}

function updateNavEnabledPill(navEnabled) {{
  const pill     = document.getElementById('navEnabledPill');
  const btnStart = document.getElementById('btnMissionStart');
  const btnStop  = document.getElementById('btnMissionStop');
  if (!pill) return;
  if (navEnabled) {{
    pill.textContent = 'nav: ENABLED'; pill.style.background = '#c8e6c9'; pill.style.color = '#1b5e20';
    if (btnStart) {{ btnStart.style.fontWeight='400'; btnStart.style.borderColor=''; btnStart.style.color=''; }}
    if (btnStop)  {{ btnStop.style.fontWeight='700';  btnStop.style.borderColor='#e53935'; btnStop.style.color='#c62828'; }}
  }} else {{
    pill.textContent = 'nav: STOPPED'; pill.style.background = '#ffcdd2'; pill.style.color = '#b71c1c';
    if (btnStart) {{ btnStart.style.fontWeight='700'; btnStart.style.borderColor='#4caf50'; btnStart.style.color='#1b5e20'; }}
    if (btnStop)  {{ btnStop.style.fontWeight='400';  btnStop.style.borderColor=''; btnStop.style.color=''; }}
  }}
}}

function safeNum(x) {{ return (typeof x==='number' && isFinite(x)) ? x : null; }}
function badge(text, cls) {{ return `<span class="${{cls}}">${{text}}</span>`; }}
function fmt1(v) {{ return v !== null ? v.toFixed(1) : '—'; }}
function fmt2(v) {{ return v !== null ? v.toFixed(2) : '—'; }}
function fmt3(v) {{ return v !== null ? v.toFixed(3) : '—'; }}

// ── Copy goal command ─────────────────────────────────────────────────────────
async function copyGoalCmd() {{
  const pre  = document.getElementById("goalCmd");
  const hint = document.getElementById("copyHint");
  if (!pre) return;
  const text = (pre.textContent || "").trim();
  if (!text) {{ if (hint) hint.textContent = "No command to copy."; return; }}
  try {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      await navigator.clipboard.writeText(text);
    }} else {{
      const ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly",""); ta.style.position="fixed"; ta.style.left="-9999px";
      document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
    }}
    if (hint) {{ hint.textContent="Copied."; setTimeout(()=>{{hint.textContent="";}},1200); }}
  }} catch(e) {{ if (hint) hint.textContent="Copy failed."; }}
}}

// ── GPS Leaflet Map ────────────────────────────────────────────────────────────
let map=null, robotMarker=null, trailLine=null, accuracyCircle=null;
let trail=[], lastLatLon=null;

function initGpsMap() {{
  map = L.map('map').setView([36.162,-85.501],18);
  L.tileLayer('/tiles/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> (offline cache)'
  }}).addTo(map);
  L.control.scale({{imperial:false,position:'bottomleft'}}).addTo(map);
  robotMarker   = L.circleMarker([36.162,-85.501],{{radius:7,weight:2,fillOpacity:0.8}}).addTo(map);
  trailLine     = L.polyline([],{{weight:3}}).addTo(map);
  accuracyCircle= L.circle([36.162,-85.501],{{radius:3,weight:1,fillOpacity:0.08}}).addTo(map);
}}

let _dz=1.0;
const _DZ_STEP=0.25, _DZ_MIN=1.0, _DZ_MAX=8.0;
function _applyDz() {{
  document.getElementById('map').style.transform=`scale(${{_dz}})`;
  const b=document.getElementById('dzoom-badge'); if(b) b.textContent=`${{_dz.toFixed(2)}}×`;
}}
function digitalZoom(dir)  {{ _dz=Math.min(_DZ_MAX,Math.max(_DZ_MIN,_dz+dir*_DZ_STEP)); _applyDz(); }}
function digitalZoomReset(){{ _dz=1.0; _applyDz(); }}
document.getElementById('map-wrapper').addEventListener('wheel',(ev)=>{{
  if(ev.ctrlKey) return; ev.preventDefault(); digitalZoom(ev.deltaY<0?1:-1);
}},{{passive:false}});
function clearTrail(){{ trail=[]; if(trailLine) trailLine.setLatLngs(trail); }}
function centerOnRobot(){{ if(map&&lastLatLon) map.setView(lastLatLon,Math.max(map.getZoom(),18)); }}

function updateGpsMapFromStatus(j) {{
  const gps=j.gps||{{}};
  const lat=safeNum(gps.lat), lon=safeNum(gps.lon);
  if(lat===null||lon===null) return;
  lastLatLon=[lat,lon];
  const last=trail.length?trail[trail.length-1]:null;
  if(!last||(Math.abs(last[0]-lat)>1e-7||Math.abs(last[1]-lon)>1e-7)) {{
    trail.push([lat,lon]); if(trail.length>MAX_TRAIL) trail.shift();
  }}
  robotMarker.setLatLng([lat,lon]);
  trailLine.setLatLngs(trail);
  const cov_xx=safeNum(gps.cov_xx),cov_yy=safeNum(gps.cov_yy);
  let sigma_m=3.0;
  if(cov_xx!==null&&cov_yy!==null&&cov_xx>0&&cov_yy>0) {{
    sigma_m=Math.sqrt(0.5*(cov_xx+cov_yy)); sigma_m=Math.min(Math.max(sigma_m,0.5),50.0);
  }}
  accuracyCircle.setLatLng([lat,lon]); accuracyCircle.setRadius(sigma_m);
  if(trail.length===1) map.setView([lat,lon],18);
  updateMissionOverlay(j);
  updateNavEnabledPill((j.mission||{{}}).nav_enabled===true);
}}

// ── Mission overlay ────────────────────────────────────────────────────────────
let _missionLayers=[];
let _anchor=null;

function _tryLockAnchor(mission) {{
  if(_anchor) return;
  const lat=safeNum(mission.origin_lat), lon=safeNum(mission.origin_lon);
  if(lat===null||lon===null) return;
  _anchor={{lat,lon,x:0.0,y:0.0}};
  console.log(`[mission] anchor: (${{lat.toFixed(7)}},${{lon.toFixed(7)}})`);
}}

function _xyToLatLon(px,py,aLat,aLon,aX,aY) {{
  const dy=py-aY, dx=px-aX;
  return [aLat+dy/111320.0, aLon+dx/(111320.0*Math.cos(aLat*Math.PI/180.0))];
}}

function _clearMissionLayers() {{ _missionLayers.forEach(l=>map.removeLayer(l)); _missionLayers=[]; }}
function _addLayer(layer) {{ layer.addTo(map); _missionLayers.push(layer); }}

function updateMissionOverlay(j) {{
  if(!map) return;
  _clearMissionLayers();
  const gps=j.gps||{{}}, mission=j.mission||{{}};
  if(!mission.present) return;
  _tryLockAnchor(mission);
  if(!_anchor) return;

  const badgeLat=safeNum(gps.lat)??_anchor.lat;
  const badgeLon=safeNum(gps.lon)??_anchor.lon;
  const toLL=(px,py)=>_xyToLatLon(px,py,_anchor.lat,_anchor.lon,_anchor.x,_anchor.y);
  const acc_r=mission.acceptance_radius_m||2.5;

  const wps=mission.waypoints;
  if(Array.isArray(wps)&&wps.length>0) {{
    _addLayer(L.polyline(wps.map(w=>[w.lat,w.lon]),{{color:'#1a73e8',weight:2,dashArray:'6 4',opacity:0.75}}));
    wps.forEach((w,i)=>{{
      const ll=[w.lat,w.lon];
      const isActive=(mission.waypoint_index===i), isPast=(mission.waypoint_index!==null&&i<mission.waypoint_index);
      const color=isActive?'#e67c00':(isPast?'#888':'#1a73e8');
      _addLayer(L.circleMarker(ll,{{radius:isActive?9:6,color,weight:2,fillColor:color,fillOpacity:isActive?0.9:0.35}}));
      if(isActive) _addLayer(L.circle(ll,{{radius:acc_r,color:'#e67c00',weight:1.5,dashArray:'4 4',fill:false,opacity:0.7}}));
      const label=w.name?`${{i}}:${{w.name}}`:String(i);
      _addLayer(L.marker(ll,{{icon:L.divIcon({{className:'',html:`<span style="font:bold 11px ui-monospace,monospace;color:${{color}};text-shadow:0 0 3px #fff,0 0 3px #fff;">${{label}}</span>`,iconAnchor:[-6,6]}}),interactive:false}}));
    }});
  }}

  if(mission.target_x!==null&&mission.target_x!==undefined&&mission.target_y!==null) {{
    const ll=toLL(mission.target_x,mission.target_y);
    _addLayer(L.circleMarker(ll,{{radius:7,color:'#d93025',weight:2,fillColor:'#d93025',fillOpacity:0.2}}));
    _addLayer(L.marker(ll,{{icon:L.divIcon({{className:'',html:`<span style="font:bold 14px sans-serif;color:#d93025;text-shadow:0 0 3px #fff;">✕</span>`,iconAnchor:[7,9]}}),interactive:false}}));
  }}

  const cx=safeNum(mission.carrot_x), cy=safeNum(mission.carrot_y);
  if(cx!==null&&cy!==null) {{
    const ll=toLL(cx,cy);
    _addLayer(L.circleMarker(ll,{{radius:7,color:'#7b2d8b',weight:2.5,fillColor:'#ce93d8',fillOpacity:0.85}}));
    _addLayer(L.marker(ll,{{icon:L.divIcon({{className:'',html:`<span style="font:bold 12px sans-serif;color:#7b2d8b;text-shadow:0 0 3px #fff;">🥕</span>`,iconAnchor:[8,8]}}),interactive:false}}));
  }}

  const idx=mission.waypoint_index!==null&&mission.waypoint_index!==undefined?mission.waypoint_index:'—';
  const total=Array.isArray(wps)?wps.length:'?';
  const done=mission.mission_complete?' ✓ COMPLETE':'';
  const carrotStr=(cx!==null&&cy!==null)?`${{cx.toFixed(1)}},${{cy.toFixed(1)}}`:'none';
  const anchorStr=_anchor?`${{_anchor.lat.toFixed(5)}},${{_anchor.lon.toFixed(5)}}`:'waiting…';
  _addLayer(L.marker([badgeLat,badgeLon],{{
    icon:L.divIcon({{className:'',
      html:`<div style="background:rgba(255,255,255,0.88);border:1px solid #ccc;border-radius:6px;padding:2px 7px;font:11px ui-monospace,monospace;white-space:nowrap;pointer-events:none;">WP ${{idx}}/${{total}}${{done}} · 🥕(${{carrotStr}}) · ⚓(${{anchorStr}})</div>`,
      iconAnchor:[-8,-8]}}),interactive:false,zIndexOffset:1000
  }}));
}}

// ── Costmap Canvas ────────────────────────────────────────────────────────────
let cmWhich="local", cmData=null, statusData=null;
let view={{x_min:-5,x_max:5,y_min:-5,y_max:5}};
let goal=null, dragStart=null;

const navCanvas=document.getElementById("navCanvas");
const navParent=document.getElementById("navview");
const ctx=navCanvas.getContext("2d");

function resizeCanvas() {{ navCanvas.width=navParent.clientWidth; navCanvas.height=navParent.clientHeight; }}
window.addEventListener("resize",()=>{{ resizeCanvas(); drawNavView(); if(map) map.invalidateSize(); }});

function toggleCostmap() {{
  cmWhich=(cmWhich==="local")?"global":"local";
  document.getElementById("cmMode").textContent="costmap: "+cmWhich;
  fetchCostmap();
}}

function fitCostmap() {{
  if(!cmData||!cmData.present||!cmData.resolution||!cmData.width||!cmData.height) return;
  const ox=cmData.origin_x, oy=cmData.origin_y;
  const w_m=cmData.width*cmData.resolution, h_m=cmData.height*cmData.resolution;
  const m=0.10;
  view.x_min=ox-w_m*m; view.x_max=ox+w_m*(1+m);
  view.y_min=oy-h_m*m; view.y_max=oy+h_m*(1+m);
  drawNavView();
}}

function clearGoal() {{
  goal=null; dragStart=null;
  document.getElementById("goalLine").textContent="—";
  document.getElementById("goalCmd").textContent="";
  drawNavView();
}}

function worldToCanvas(x,y) {{
  const W=navCanvas.width,H=navCanvas.height;
  const u=(x-view.x_min)/(view.x_max-view.x_min);
  const v=(y-view.y_min)/(view.y_max-view.y_min);
  return [u*W,(1-v)*H];
}}

function canvasToWorld(cx,cy) {{
  const W=navCanvas.width,H=navCanvas.height;
  const u=cx/W, v=1-(cy/H);
  return [view.x_min+u*(view.x_max-view.x_min), view.y_min+v*(view.y_max-view.y_min)];
}}

function drawCostmap() {{
  if(!cmData||!cmData.present||!cmData.gray||cmData.gray.length===0) {{
    ctx.clearRect(0,0,navCanvas.width,navCanvas.height);
    ctx.fillStyle="#ffffff"; ctx.fillRect(0,0,navCanvas.width,navCanvas.height);
    ctx.fillStyle="#666"; ctx.fillText("Costmap not available",20,30);
    return;
  }}
  const rw=cmData.render_w, rh=cmData.render_h, gray=cmData.gray;
  const img=ctx.createImageData(rw,rh);
  for(let i=0;i<rw*rh;i++) {{
    const g=gray[i]; img.data[i*4]=g; img.data[i*4+1]=g; img.data[i*4+2]=g; img.data[i*4+3]=255;
  }}
  const off=document.createElement("canvas"); off.width=rw; off.height=rh;
  const octx=off.getContext("2d"); octx.putImageData(img,0,0);
  const ox=cmData.origin_x, oy=cmData.origin_y;
  const w_m=cmData.width*cmData.resolution, h_m=cmData.height*cmData.resolution;
  const [x0,y0]=worldToCanvas(ox,oy), [x1,y1]=worldToCanvas(ox+w_m,oy+h_m);
  const left=Math.min(x0,x1),top=Math.min(y0,y1),right=Math.max(x0,x1),bottom=Math.max(y0,y1);
  ctx.clearRect(0,0,navCanvas.width,navCanvas.height);
  ctx.imageSmoothingEnabled=false;
  ctx.drawImage(off,left,top,(right-left),(bottom-top));
  ctx.save(); ctx.strokeStyle="rgba(0,0,0,0.12)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.rect(left,top,(right-left),(bottom-top)); ctx.stroke(); ctx.restore();
}}

function drawRobotPose() {{
  if(!statusData||!statusData.localization) return;
  const loc=statusData.localization;
  const x=safeNum(loc.x), y=safeNum(loc.y), yaw=safeNum(loc.yaw_rad);
  if(x===null||y===null||yaw===null) return;
  const [cx,cy]=worldToCanvas(x,y);
  const [cx_r]=worldToCanvas(x+0.40,y);
  const r_px=Math.max(6,Math.abs(cx_r-cx));
  ctx.save(); ctx.strokeStyle="rgba(30,90,200,0.55)"; ctx.lineWidth=2;
  ctx.beginPath(); ctx.arc(cx,cy,r_px,0,Math.PI*2); ctx.stroke(); ctx.restore();
  ctx.save(); ctx.fillStyle="rgba(30,90,200,0.95)";
  ctx.beginPath(); ctx.arc(cx,cy,5,0,Math.PI*2); ctx.fill(); ctx.restore();
  const len=18, hx=cx+len*Math.cos(yaw), hy=cy-len*Math.sin(yaw);
  ctx.save(); ctx.strokeStyle="rgba(30,90,200,0.95)"; ctx.lineWidth=2;
  ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(hx,hy); ctx.stroke(); ctx.restore();
  ctx.save(); ctx.font="12px ui-monospace,monospace"; ctx.fillStyle="rgba(30,90,200,0.95)";
  ctx.fillText(`(${{x.toFixed(2)}},${{y.toFixed(2)}})`,cx+8,cy-8); ctx.restore();
}}

function drawGoalPose() {{
  if(!goal) return;
  const [cx,cy]=worldToCanvas(goal.x,goal.y);
  ctx.save(); ctx.fillStyle="rgba(200,40,40,0.95)";
  ctx.beginPath(); ctx.arc(cx,cy,5,0,Math.PI*2); ctx.fill();
  const len=18, hx=cx+len*Math.cos(goal.yaw), hy=cy-len*Math.sin(goal.yaw);
  ctx.strokeStyle="rgba(200,40,40,0.95)"; ctx.lineWidth=2;
  ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(hx,hy); ctx.stroke(); ctx.restore();
}}

function drawPath() {{
  if(!statusData||!statusData.path||!statusData.path.present) return;
  const pts=statusData.path.points_xy;
  if(!pts||pts.length<4) return;
  ctx.save();
  ctx.strokeStyle="rgba(0,180,0,0.8)";
  ctx.lineWidth=2;
  ctx.setLineDash([4,3]);
  ctx.beginPath();
  for(let i=0;i<pts.length-1;i+=2) {{
    const [cx,cy]=worldToCanvas(pts[i],pts[i+1]);
    if(i===0) ctx.moveTo(cx,cy);
    else ctx.lineTo(cx,cy);
  }}
  ctx.stroke();
  // Draw goal point at end of path
  if(pts.length>=2) {{
    const [ex,ey]=worldToCanvas(pts[pts.length-2],pts[pts.length-1]);
    ctx.setLineDash([]);
    ctx.fillStyle="rgba(0,180,0,0.9)";
    ctx.beginPath(); ctx.arc(ex,ey,5,0,Math.PI*2); ctx.fill();
  }}
  ctx.restore();
}}

function drawCmdVelArrow() {{
  if(!statusData||!statusData.localization||!statusData.cmd_vel) return;
  const loc=statusData.localization;
  const cv=statusData.cmd_vel;
  const x=safeNum(loc.x), y=safeNum(loc.y), yaw=safeNum(loc.yaw_rad);
  const vx=safeNum(cv.vx), wz=safeNum(cv.wz);
  if(x===null||y===null||yaw===null||vx===null) return;
  if(Math.abs(vx)<0.01&&(wz===null||Math.abs(wz)<0.01)) return;

  const [cx,cy]=worldToCanvas(x,y);

  // Linear velocity arrow (orange = forward, red = backward)
  if(Math.abs(vx)>0.01) {{
    const len=vx*40;  // 1 m/s = 40px
    const hx=cx+len*Math.cos(yaw);
    const hy=cy-len*Math.sin(yaw);
    const color=vx>=0?"rgba(255,140,0,0.95)":"rgba(200,0,0,0.95)";
    ctx.save();
    ctx.strokeStyle=color; ctx.lineWidth=3;
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(hx,hy); ctx.stroke();
    // Arrowhead
    const ang=Math.atan2(hy-cy,hx-cx);
    ctx.beginPath();
    ctx.moveTo(hx,hy);
    ctx.lineTo(hx-10*Math.cos(ang-0.4),hy-10*Math.sin(ang-0.4));
    ctx.lineTo(hx-10*Math.cos(ang+0.4),hy-10*Math.sin(ang+0.4));
    ctx.closePath();
    ctx.fillStyle=color; ctx.fill();
    ctx.restore();
  }}

  // Angular velocity arc (cyan = left, magenta = right)
  if(wz!==null&&Math.abs(wz)>0.05) {{
    const arcR=20;
    const arcSpan=Math.min(Math.abs(wz)*0.8, Math.PI);
    const color=wz>0?"rgba(0,180,220,0.9)":"rgba(180,0,200,0.9)";
    const startAng=-yaw;
    const endAng=wz>0?startAng-arcSpan:startAng+arcSpan;
    ctx.save();
    ctx.strokeStyle=color; ctx.lineWidth=2;
    ctx.beginPath();
    ctx.arc(cx,cy,arcR,startAng,endAng,wz>0);
    ctx.stroke();
    ctx.restore();
  }}

  // Speed label
  ctx.save();
  ctx.font="11px ui-monospace,monospace";
  ctx.fillStyle="rgba(255,140,0,0.95)";
  ctx.fillText(`${{vx.toFixed(2)}}m/s`,cx+8,cy+20);
  ctx.restore();
}}

function drawNavView() {{
  resizeCanvas(); drawCostmap(); drawPath(); drawRobotPose(); drawCmdVelArrow(); drawGoalPose();
  ctx.save(); ctx.font="12px ui-monospace,monospace"; ctx.fillStyle="rgba(0,0,0,0.75)";
  const loc=(statusData&&statusData.localization)?statusData.localization:null;
  const cmf=(cmData&&cmData.frame_id)?cmData.frame_id:"—";
  const lf=(loc&&loc.frame_id)?loc.frame_id:"—";
  const x=(loc&&typeof loc.x==="number")?loc.x.toFixed(2):"—";
  const y=(loc&&typeof loc.y==="number")?loc.y.toFixed(2):"—";
  ctx.fillText(`cm_frame=${{cmf}}  loc_frame=${{lf}}  loc=(${{x}},${{y}})`,10,18);
  ctx.restore();
}}

function setGoal(x,y,yaw) {{
  goal={{x,y,yaw}};
  document.getElementById("goalLine").textContent=`x=${{x.toFixed(2)}}, y=${{y.toFixed(2)}}, yaw=${{(yaw*180/Math.PI).toFixed(1)}} deg`;
  document.getElementById("yawDeg").value=(yaw*180/Math.PI).toFixed(1);
  const qz=Math.sin(yaw/2.0), qw=Math.cos(yaw/2.0);
  document.getElementById("goalCmd").textContent=
`ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{
  pose: {{
    header: {{ frame_id: map }},
    pose: {{
      position: {{ x: ${{x.toFixed(3)}}, y: ${{y.toFixed(3)}}, z: 0.0 }},
      orientation: {{ x: 0.0, y: 0.0, z: ${{qz.toFixed(6)}}, w: ${{qw.toFixed(6)}} }}
    }}
  }}
}}"`;
  drawNavView();
}}

function updateGoalYawFromInput() {{
  if(!goal) return;
  const deg=parseFloat(document.getElementById("yawDeg").value);
  if(!isFinite(deg)) return;
  goal.yaw=deg*Math.PI/180.0; setGoal(goal.x,goal.y,goal.yaw);
}}

navCanvas.addEventListener("mousedown",(ev)=>{{
  const rect=navCanvas.getBoundingClientRect();
  const [x,y]=canvasToWorld(ev.clientX-rect.left,ev.clientY-rect.top);
  const yaw=(goal&&typeof goal.yaw==="number")?goal.yaw:0.0;
  setGoal(x,y,yaw); dragStart={{x,y,cx:ev.clientX-rect.left,cy:ev.clientY-rect.top}};
}});
navCanvas.addEventListener("mousemove",(ev)=>{{
  if(!dragStart||!goal) return;
  const rect=navCanvas.getBoundingClientRect();
  const [x2,y2]=canvasToWorld(ev.clientX-rect.left,ev.clientY-rect.top);
  const dx=x2-goal.x, dy=y2-goal.y;
  if(Math.sqrt(dx*dx+dy*dy)<0.2) return;
  setGoal(goal.x,goal.y,Math.atan2(dy,dx));
}});
navCanvas.addEventListener("mouseup",()=>{{dragStart=null;}});
navCanvas.addEventListener("mouseleave",()=>{{dragStart=null;}});

// ── NEW: update navigation status panel ───────────────────────────────────────
function btStatusClass(s) {{
  if(s==='RUNNING') return 'bt-running';
  if(s==='SUCCESS') return 'bt-success';
  if(s==='FAILURE') return 'bt-failure';
  return 'bt-idle';
}}

function updateNavStatusPanel(j) {{
  const bt       = j.bt      || {{}};
  const cv       = j.cmd_vel || {{}};
  const mavros   = j.mavros  || {{}};
  const nav      = j.nav     || {{}};
  const now      = j.time_unix || (Date.now()/1000);

  // ── Recovery pill ──
  const recovPill  = document.getElementById('recoveryPill');
  const recovCount = document.getElementById('recoveryCount');
  if(bt.recovery_active) {{
    recovPill.style.display='inline-block';
  }} else {{
    recovPill.style.display='none';
  }}
  if(bt.recovery_count>0) {{
    recovCount.textContent=`(recoveries: ${{bt.recovery_count}})`;
  }}

  // ── cmd_vel ──
  const vx=safeNum(cv.vx), wz=safeNum(cv.wz);
  document.getElementById('cvVx').textContent = vx!==null ? `${{vx.toFixed(3)}} m/s` : '—';
  document.getElementById('cvWz').textContent = wz!==null ? `${{wz.toFixed(3)}} rad/s` : '—';
  const vxBar=document.getElementById('cvVxBar');
  if(vxBar&&vx!==null) {{
    const pct=Math.min(100,Math.abs(vx)/1.0*100);
    vxBar.style.width=pct+'%';
    vxBar.style.background=vx>=0?'#1565c0':'#c62828';
  }}

  // ── topbar quick stats ──
  document.getElementById('topVx').textContent = vx!==null ? `${{vx.toFixed(2)}} m/s` : '—';

  // ── MAVROS ──
  const mavConn = document.getElementById('mavConnected');
  const mavArm  = document.getElementById('mavArmed');
  const mavMode = document.getElementById('mavMode');
  const mavBatt = document.getElementById('mavBattery');
  const topMav  = document.getElementById('topMavros');

  if(mavros.present) {{
    mavConn.innerHTML = mavros.connected ? badge('YES','ok') : badge('NO','bad');
    mavArm.innerHTML  = mavros.armed     ? badge('ARMED','warn') : badge('DISARMED','ok');
    mavMode.textContent = mavros.mode || '—';
    if(mavros.battery_voltage!==null&&mavros.battery_voltage!==undefined) {{
      const pct = mavros.battery_remaining!==null
        ? ` (${{(mavros.battery_remaining*100).toFixed(0)}}%)`
        : '';
      mavBatt.textContent=`${{mavros.battery_voltage.toFixed(1)}}V${{pct}}`;
      mavBatt.className = mavros.battery_remaining!==null&&mavros.battery_remaining<0.2
        ? 'mono bad' : 'mono';
    }} else {{
      mavBatt.textContent='—';
    }}
    topMav.textContent=`APM: ${{mavros.mode||'?'}} ${{mavros.armed?'⚡':'○'}}`;
    topMav.className = mavros.connected ? 'ok' : 'bad';
  }} else {{
    mavConn.innerHTML=badge('N/A','muted');
    mavArm.textContent='—'; mavMode.textContent='—'; mavBatt.textContent='—';
    topMav.textContent='APM: —'; topMav.className='muted';
  }}

  // ── BT node status ──
  const fpEl = document.getElementById('btFollowPath');
  const cpEl = document.getElementById('btComputePath');
  const naEl = document.getElementById('navActive');
  if(bt.present) {{
    fpEl.innerHTML = `<span class="${{btStatusClass(bt.follow_path_status)}}">${{bt.follow_path_status||'—'}}</span>`;
    cpEl.innerHTML = `<span class="${{btStatusClass(bt.compute_path_status)}}">${{bt.compute_path_status||'—'}}</span>`;
  }} else {{
    fpEl.textContent='—'; cpEl.textContent='—';
  }}
  naEl.innerHTML = nav.status_summary==='active'
    ? badge('ACTIVE','ok') : badge(nav.status_summary||'idle','muted');

  // ── topbar BT status ──
  const topBT = document.getElementById('topBTStatus');
  if(bt.recovery_active) {{
    topBT.innerHTML = badge('BT: RECOVERY','bad');
  }} else if(bt.follow_path_status==='RUNNING') {{
    topBT.innerHTML = badge('BT: FOLLOWING','ok');
  }} else {{
    topBT.textContent = `BT: ${{bt.follow_path_status||'—'}}`;
    topBT.className   = 'muted';
  }}

  // ── BT event log ──
  const tbody = document.getElementById('btEventsTbody');
  const events = bt.last_events || [];
  if(events.length===0) {{
    tbody.innerHTML='<tr><td colspan="3" class="muted">No events yet</td></tr>';
  }} else {{
    const rows = [...events].reverse().map(ev=>{{
      const age = (now - ev.stamp_unix);
      const ageStr = age<60 ? `${{age.toFixed(1)}}s` : `${{(age/60).toFixed(1)}}m`;
      const cls = btStatusClass(ev.current_status);
      return `<tr>
        <td class="mono">${{ev.node_name}}</td>
        <td><span class="${{cls}}">${{ev.current_status}}</span></td>
        <td class="muted">${{ageStr}}</td>
      </tr>`;
    }}).join('');
    tbody.innerHTML=rows;
  }}
}}

// ── Update diagnostics panel ──────────────────────────────────────────────────
function updateDiagPanel(j) {{
  const v = j.vesc_left || {{}};
  const loc = j.localization || {{}};

  function setMono(id, val, suffix) {{
    const el=document.getElementById(id);
    if(!el) return;
    el.textContent = val!==null&&val!==undefined ? val.toFixed(2)+suffix : '—';
  }}
  function setMonoRaw(id, val) {{
    const el=document.getElementById(id);
    if(!el) return;
    el.textContent = val!==null&&val!==undefined ? String(val) : '—';
  }}

  setMono('vescVolt',    v.input_voltage_v, ' V');
  setMono('vescCurrIn',  v.input_current_a, ' A');
  setMono('vescCurrMot', v.motor_current_a, ' A');
  setMono('vescDuty',    v.duty,            '');
  setMono('vescErpm',    v.erpm,            '');

  const tFet = document.getElementById('vescTempFet');
  const tMot = document.getElementById('vescTempMot');
  if(tFet) {{
    tFet.textContent = v.temp_fet_c!==null&&v.temp_fet_c!==undefined ? v.temp_fet_c.toFixed(1)+'°C' : '—';
    tFet.className   = 'mono' + (v.temp_fet_c!==null&&v.temp_fet_c>70?' bad':'');
  }}
  if(tMot) {{
    tMot.textContent = v.temp_motor_c!==null&&v.temp_motor_c!==undefined ? v.temp_motor_c.toFixed(1)+'°C' : '—';
    tMot.className   = 'mono' + (v.temp_motor_c!==null&&v.temp_motor_c>80?' bad':'');
  }}

  const faultEl=document.getElementById('vescFault');
  if(faultEl) {{
    faultEl.textContent = v.fault_code!==null&&v.fault_code!==undefined ? String(v.fault_code) : '—';
    faultEl.className   = 'mono' + (v.fault_code&&v.fault_code!==0?' bad':'');
  }}

  setMono('locX',     loc.x,       ' m');
  setMono('locY',     loc.y,       ' m');
  const yawEl=document.getElementById('locYaw');
  if(yawEl) yawEl.textContent = loc.yaw_rad!==null&&loc.yaw_rad!==undefined
    ? `${{(loc.yaw_rad*180/Math.PI).toFixed(1)}}°` : '—';
  setMono('locCovXX', loc.cov_xx,  '');
  setMono('locCovYY', loc.cov_yy,  '');
  const frEl=document.getElementById('locFrame');
  if(frEl) frEl.textContent=loc.frame_id||'—';
}}

// ── Update GPS/health (top bar + left panel) ───────────────────────────────────
function updateLeftPanel(j) {{
  const gps=j.gps||{{}}, sats=j.gps_sats||{{}}, validity=j.gps_validity||{{}};
  const lat=safeNum(gps.lat), lon=safeNum(gps.lon);
  document.getElementById('gpsLine').textContent =
    (lat!==null&&lon!==null) ? `${{lat.toFixed(7)}}, ${{lon.toFixed(7)}}` : '—';

  const sv=(sats.satellites_visible!==null&&sats.satellites_visible!==undefined)?sats.satellites_visible:null;
  document.getElementById('satLine').textContent = sv!==null?String(sv):'—';

  const cov_xx=safeNum(gps.cov_xx), cov_yy=safeNum(gps.cov_yy);
  if(cov_xx!==null&&cov_yy!==null&&cov_xx>0&&cov_yy>0) {{
    document.getElementById('covLine').textContent=`σx=${{Math.sqrt(cov_xx).toFixed(2)}}m, σy=${{Math.sqrt(cov_yy).toFixed(2)}}m`;
  }} else document.getElementById('covLine').textContent='—';

  const now=(typeof j.time_unix==='number')?j.time_unix:(Date.now()/1000.0);
  const age=(typeof gps.stamp_unix==='number')?(now-gps.stamp_unix):null;
  document.getElementById('ageLine').textContent=age!==null?age.toFixed(2):'—';

  let cls=validity.cls||'unknown', reason=validity.reason||'unknown';
  let badgeCls='muted';
  if(cls==='good') badgeCls='ok';
  else if(cls==='degraded') badgeCls='warn';
  else if(cls==='poor'||cls==='no_fix') badgeCls='bad';
  const extra=(validity.rms_cov_m!==null&&validity.rms_cov_m!==undefined)
    ? ` | rms_cov=${{Number(validity.rms_cov_m).toFixed(2)}}m` : '';
  document.getElementById('gpsValidLine').innerHTML=
    `${{badge(cls,badgeCls)}} <span class="muted">(${{reason}})</span>${{extra}}`;

  const healthOk=j.health&&j.health.ok===true;
  const badgeEl=document.getElementById('healthBadge');
  badgeEl.textContent=`Health: ${{healthOk?'OK':'CHECK'}}`;
  badgeEl.className=healthOk?'ok':'bad';

  const tf=j.tf||{{}};
  function tfLine(ok,name) {{ return `${{ok?badge('OK','ok'):badge('MISSING','bad')}}  ${{name}}`; }}
  document.getElementById('tfPanel').innerHTML=[
    tfLine(tf.map_to_odom,'map→odom'),
    tfLine(tf.odom_to_base,'odom→base_link'),
    tfLine(tf.map_to_base,'map→base_link'),
  ].join('\\n');

  const f=j.topic_freshness||{{}};
  const flines=Object.keys(f).sort().map(k=>{{
    const o=f[k];
    const p=o.present?badge('P','ok'):badge('A','bad');
    const a=(o.age_sec===null||o.age_sec===undefined)?'—':o.age_sec.toFixed(2);
    const hz=(o.ema_hz===null||o.ema_hz===undefined)?'—':o.ema_hz.toFixed(1);
    return `${{p}}  ${{k.padEnd(14)}}  age=${{a}}s  hz=${{hz}}`;
  }});
  document.getElementById('freshness').textContent=flines.join('\\n');
  document.getElementById('health').textContent=JSON.stringify(j.health,null,2);
}}

// ── Fetch /status and /costmap ────────────────────────────────────────────────
async function fetchCostmap() {{
  try {{
    const r=await fetch(`/costmap/${{cmWhich}}`,{{cache:'no-store',headers:fetchHeaders()}});
    if(!r.ok) throw new Error(`HTTP ${{r.status}}`);
    cmData=await r.json();
    if(cmData&&cmData.present) fitCostmap();
    drawNavView();
  }} catch(e) {{ drawNavView(); }}
}}

async function refresh() {{
  try {{
    const r=await fetch('/status',{{cache:'no-store',headers:fetchHeaders()}});
    if(!r.ok) throw new Error(`HTTP ${{r.status}}`);
    const j=await r.json();
    statusData=j;
    document.getElementById('status').textContent=JSON.stringify(j,null,2);
    updateLeftPanel(j);
    updateGpsMapFromStatus(j);
    updateNavStatusPanel(j);   // NEW
    updateDiagPanel(j);        // NEW
    drawNavView();
  }} catch(e) {{
    document.getElementById('health').textContent=JSON.stringify({{ok:false,error:String(e)}},null,2);
  }}
}}

initGpsMap();
resizeCanvas();
fetchCostmap();
refresh();
setInterval(refresh, 1000);
setInterval(fetchCostmap, 1000);
setTimeout(()=>{{ if(map) map.invalidateSize(); }}, 0);
requestAnimationFrame(()=>{{ if(map) map.invalidateSize(); }});
</script>
</body>
</html>
"""