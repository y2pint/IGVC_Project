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
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 12px; height: 100vh; display: flex; flex-direction: column; gap: 10px; background: #f5f5f5; }}

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

    /* ── Bottom split ── */
    #bottom {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
      flex: 1; min-height: 0;
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

    #map {{ flex: 1; border-radius: 8px; border: 1px solid #ddd; min-height: 0; }}
    #map-wrapper {{
      flex: 1; min-height: 0; position: relative;
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
    #navview {{ flex: 1; border-radius: 8px; border: 1px solid #ddd; background: #fff; position: relative; min-height: 0; overflow: hidden; }}
    #navCanvas {{ width: 100%; height: 100%; display: block; }}

    /* ── Shared utilities ── */
    .row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .kv {{ display: grid; grid-template-columns: 150px 1fr; gap: 4px 8px; font-size: 13px; }}
    .muted {{ color: #666; font-size: 12px; }}
    .ok {{ color: #136f2d; font-weight: 700; }}
    .bad {{ color: #a11; font-weight: 700; }}
    .warn {{ color: #b36b00; font-weight: 700; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    pre {{ background: #f7f7f7; padding: 8px; border-radius: 8px; overflow: auto; max-height: 220px; margin: 4px 0 0; }}
    .pill {{ padding: 2px 8px; border-radius: 999px; border: 1px solid #ddd; font-size: 12px; }}
    input {{ padding: 6px; font-size: 13px; border: 1px solid #ccc; border-radius: 6px; }}
    hr {{ border: none; border-top: 1px solid #eee; margin: 6px 0; }}

    /* ── Battery indicator ── */
    .battery-widget {{
      display: flex; align-items: center; gap: 6px; font-size: 13px;
    }}
    .battery-bar-wrap {{
      width: 52px; height: 14px; border: 1.5px solid #aaa; border-radius: 3px;
      position: relative; background: #f0f0f0; overflow: visible;
    }}
    .battery-bar-wrap::after {{
      content: ''; position: absolute; right: -5px; top: 3px;
      width: 4px; height: 6px; background: #aaa; border-radius: 0 2px 2px 0;
    }}
    .battery-bar-fill {{
      height: 100%; border-radius: 2px 0 0 2px; transition: width 0.5s, background 0.5s;
    }}
    .battery-voltage {{ font-family: ui-monospace, monospace; font-size: 12px; }}

    /* collapsible details in left panel */
    details summary {{ cursor: pointer; font-size: 13px; font-weight: 600; margin: 6px 0 4px; }}
    details[open] summary {{ margin-bottom: 6px; }}

    /* ── Waypoint Editor Modal ── */
    #wpEditorOverlay {{
      display: none; position: fixed; inset: 0; z-index: 9999;
      background: rgba(0,0,0,0.45);
      align-items: center; justify-content: center;
    }}
    #wpEditorOverlay.open {{ display: flex; }}
    #wpEditor {{
      background: #fff; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.25);
      width: 92vw; max-width: 1100px; height: 82vh;
      display: grid; grid-template-columns: 1fr 340px; overflow: hidden;
    }}
    #wpEditorMap {{ width: 100%; height: 100%; }}
    #wpEditorSidebar {{
      display: flex; flex-direction: column; border-left: 1px solid #ddd;
      font-size: 13px; overflow: hidden;
    }}
    #wpEditorSidebar h3 {{ margin: 0; padding: 12px 14px 8px; font-size: 14px; border-bottom: 1px solid #eee; }}
    #wpEditorSidebar .sidebar-body {{ flex: 1; overflow-y: auto; padding: 8px 10px; }}
    #wpEditorSidebar .sidebar-footer {{ padding: 10px; border-top: 1px solid #eee; display: flex; flex-direction: column; gap: 6px; }}
    #wpList {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }}
    #wpList li {{
      display: flex; align-items: center; gap: 6px;
      background: #f8f8f8; border: 1px solid #e0e0e0; border-radius: 6px; padding: 4px 6px;
      cursor: grab;
    }}
    #wpList li.drag-over {{ border-color: #1a73e8; background: #e8f0fe; }}
    #wpList li .wp-idx {{ color: #888; font-size: 11px; min-width: 18px; text-align: right; }}
    #wpList li input {{
      flex: 1; border: none; background: transparent; font-size: 12px; padding: 2px 4px;
      outline: none; min-width: 0;
    }}
    #wpList li input:focus {{ background: #fff; border: 1px solid #aaa; border-radius: 4px; }}
    #wpList li .wp-coords {{ color: #999; font-size: 10px; white-space: nowrap; font-family: monospace; }}
    #wpList li .wp-del {{ cursor: pointer; color: #c00; font-size: 14px; padding: 0 2px; flex-shrink: 0; }}
    #wpList li .wp-del:hover {{ color: #f00; }}
    .wp-mode-btn {{
      padding: 5px 10px; font-size: 12px; border-radius: 6px; border: 1px solid #ccc;
      background: #fafafa; cursor: pointer; white-space: nowrap;
    }}
    .wp-mode-btn.active {{ background: #1a73e8; color: #fff; border-color: #1a73e8; }}
    .wp-mode-btn:hover:not(.active) {{ background: #eef; }}
    .wp-action-btn {{
      width: 100%; padding: 7px; font-size: 13px; border-radius: 6px; border: 1px solid #ccc;
      background: #fafafa; cursor: pointer; text-align: center;
    }}
    .wp-action-btn:hover {{ background: #eef; }}
    .wp-action-btn.primary {{ background: #1a73e8; color: #fff; border-color: #1a73e8; }}
    .wp-action-btn.primary:hover {{ background: #1558b0; }}
    .wp-action-btn.danger {{ color: #c00; }}
    .wp-action-btn.danger:hover {{ background: #fee; border-color: #f99; }}
    #wpEditorHint {{ font-size: 11px; color: #666; text-align: center; padding: 4px 0; }}
    #wpPreviewBanner {{
      display: none; background: #fff3cd; border: 1px solid #ffc107;
      border-radius: 6px; padding: 8px 12px; font-size: 12px; color: #856404;
      margin-bottom: 6px;
    }}
  </style>
</head>

<body>

  <!-- ══════════════════════════════════════════════
       TOP BAR — status at a glance + all controls
  ═══════════════════════════════════════════════ -->
  <div id="topbar">
    <h2>IGVC Status Monitor</h2>

    <div class="sep"></div>

    <!-- Status indicators -->
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
      <div class="battery-widget" title="Battery voltage (L/R VESC input)">
        <span class="muted">Batt:</span>
        <div class="battery-bar-wrap">
          <div class="battery-bar-fill" id="battFill" style="width:0%;background:#4caf50;"></div>
        </div>
        <span class="battery-voltage" id="battVolts">—</span>
      </div>
      <span class="muted">|</span>
      <span class="muted" style="font-size:11px;">1 Hz</span>
    </div>

    <!-- Buttons -->
    <div class="btn-group">
      <!-- GPS map buttons -->
      <button onclick="centerOnRobot()">⊕ Center GPS</button>
      <button onclick="clearTrail()">✕ Clear Trail</button>
      <button onclick="_anchor=null" title="Re-lock the XY→lat/lon projection anchor on next update">↺ Reset Anchor</button>
      <div class="sep"></div>
      <!-- Mission control -->
      <button id="btnMissionStart" onclick="missionCommand('start')"
              title="Reset waypoints to index 0 and enable navigation">▶ Start</button>
      <button id="btnMissionStop" onclick="missionCommand('stop')"
              title="Disable navigation — carrot_to_nav2 cancels current Nav2 goal">⏹ Stop</button>
      <button onclick="missionCommand('next')"
              title="Advance to next waypoint">⏭ Next WP</button>
      <button onclick="missionCommand('cancel')"
              title="Send one-shot cancel to Nav2 without disabling">✕ Cancel Goal</button>
      <button onclick="missionCommand('reset')"
              title="Re-lock GPS origin to current position">⚓ Reset Origin</button>
      <button onclick="openWpEditor()" title="Open waypoint editor" style="background:#e8f0fe;border-color:#1a73e8;color:#1a73e8;">✏ Edit Waypoints</button>
      <span id="navEnabledPill" class="pill" style="background:#e0e0e0;color:#555">nav: ?</span>
      <span id="missionCmdHint" class="muted"></span>
      <div class="sep"></div>
      <!-- Nav2 / costmap buttons -->
      <span class="pill" id="cmMode">costmap: local</span>
      <button onclick="toggleCostmap()">⇄ Toggle Costmap</button>
      <button onclick="fitCostmap()">⤢ Fit</button>
      <button onclick="clearGoal()">✕ Clear Goal</button>
      <div class="sep"></div>
      <button onclick="refresh()">↺ Refresh</button>
    </div>
  </div>

  <!-- ══════════════════════════════════════════════
       BOTTOM — GPS map (left) | Nav2 view (right)
  ═══════════════════════════════════════════════ -->
  <div id="bottom">

    <!-- ── LEFT: GPS Map ── -->
    <div class="panel">
      <div class="panel-header">
        <h3>GPS Map (OSM)</h3>
        <span class="muted" style="margin-left:4px;">lat/lon · requires internet</span>
        <span class="muted" style="margin-left:8px; font-size:11px;">Tile:</span>
        <button onclick="map.zoomIn()"  style="font-size:15px; line-height:1; padding:2px 8px;">+</button>
        <button onclick="map.zoomOut()" style="font-size:15px; line-height:1; padding:2px 8px;">−</button>
        <span class="muted" style="margin-left:6px; font-size:11px;">Digital:</span>
        <button onclick="digitalZoom(1)"  style="font-size:15px; line-height:1; padding:2px 8px;">+</button>
        <button onclick="digitalZoom(-1)" style="font-size:15px; line-height:1; padding:2px 8px;">−</button>
        <button onclick="digitalZoomReset()" style="font-size:11px; padding:3px 7px;">1×</button>

        <!-- Collapsible diagnostics pulled into the map panel -->
        <details style="margin-left:auto;">
          <summary>Diagnostics ▾</summary>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:6px;">
            <div>
              <div style="font-size:12px; font-weight:600; margin-bottom:4px;">TF Health</div>
              <pre id="tfPanel" class="mono" style="max-height:120px;"></pre>
            </div>
            <div>
              <div style="font-size:12px; font-weight:600; margin-bottom:4px;">Freshness (Age / Hz)</div>
              <pre id="freshness" class="mono" style="max-height:120px;"></pre>
            </div>
          </div>
          <div style="margin-top:6px;">
            <div style="font-size:12px; font-weight:600; margin-bottom:4px;">Health JSON</div>
            <pre id="health" style="max-height:120px;"></pre>
          </div>
        </details>
      </div>

      <div id="map-wrapper">
        <div id="map"></div>
        <div id="dzoom-badge">1.75×</div>
        <div id="hdgBadge" style="position:absolute;top:6px;left:6px;z-index:1000;
          background:rgba(255,255,255,0.88);border:1px solid #ccc;border-radius:6px;
          padding:2px 7px;font-size:11px;font-family:ui-monospace,monospace;
          pointer-events:none;">⌖ heading: —</div>
      </div>
    </div>

    <!-- ── RIGHT: Nav2 / Costmap ── -->
    <div class="panel">
      <div class="panel-header">
        <h3>Nav2 View</h3>
        <span class="pill">meters</span>

        <!-- Goal pose inline -->
        <span class="muted" style="margin-left:8px;">Goal:</span>
        <span id="goalLine" class="mono muted">—</span>
        <span class="muted">Yaw:</span>
        <input id="yawDeg" type="number" value="0" style="width:80px;" onchange="updateGoalYawFromInput()"/>
        <button onclick="copyGoalCmd()" style="margin-left:4px;">⎘ Copy cmd</button>
        <span id="copyHint" class="muted"></span>
      </div>

      <!-- Hidden pre so the copy logic still works -->
      <pre id="goalCmd" class="mono" style="max-height:0; padding:0; margin:0; overflow:hidden; border:none; background:none;"></pre>

      <div id="navview">
        <canvas id="navCanvas"></canvas>
      </div>
      <div class="muted" style="margin-top:6px; font-size:11px;">
        Click to set goal · drag to set yaw · pose: /odometry/filtered · costmap: OccupancyGrid
      </div>
    </div>

  </div>

  <!-- ══════════════════════════════════════════════
       WAYPOINT EDITOR MODAL
  ═══════════════════════════════════════════════ -->
  <div id="wpEditorOverlay">
    <div id="wpEditor">
      <!-- Left: map for clicking/previewing -->
      <div id="wpEditorMap"></div>

      <!-- Right: sidebar -->
      <div id="wpEditorSidebar">
        <h3>
          Waypoint Editor
          <span style="float:right;cursor:pointer;font-weight:400;color:#888;" onclick="closeWpEditor()">✕</span>
        </h3>

        <div class="sidebar-body">
          <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;">
            <button class="wp-mode-btn active" id="btnModeAdd" onclick="setWpMode('add')">+ Add on click</button>
            <button class="wp-mode-btn" id="btnModePan" onclick="setWpMode('pan')">✋ Pan</button>
          </div>
          <div id="wpEditorHint">Click on the map to place a waypoint</div>
          <hr style="margin:8px 0;">
          <div style="font-size:12px;color:#666;margin-bottom:4px;">
            Waypoints — drag to reorder
          </div>
          <ul id="wpList"></ul>

          <div id="wpPreviewBanner">
            Preview mode — waypoints not yet sent to robot.
            <a href="#" onclick="confirmSendWaypoints();return false;">Send live</a> or
            <a href="#" onclick="cancelPreview();return false;">cancel</a>.
          </div>
        </div>

        <div class="sidebar-footer">
          <div style="display:flex;gap:6px;">
            <button class="wp-action-btn" onclick="loadWpFile()" title="Load YAML or JSON waypoints file">📂 Load file</button>
            <button class="wp-action-btn" onclick="exportWaypoints()" title="Download current waypoints as YAML">💾 Export YAML</button>
          </div>
          <button class="wp-action-btn" onclick="saveWaypointsToRobot()" title="Save to robot's waypoints_file via ROS2 service">💾 Save to robot file</button>
          <button class="wp-action-btn primary" onclick="confirmSendWaypoints()">▶ Send to robot</button>
          <button class="wp-action-btn danger" onclick="clearAllWaypoints()">🗑 Clear all</button>
          <input type="file" id="wpFileInput" accept=".yaml,.yml,.json" style="display:none" onchange="onWpFileSelected(event)">
        </div>
      </div>
    </div>
  </div>

  <!-- Hidden full-status pre (used by JS only, not shown) -->
  <pre id="status" style="display:none;"></pre>

<script>
const DS_API_KEY = {repr(key_for_browser)};
const MAX_TRAIL = 300;

function fetchHeaders() {{
  if (DS_API_KEY && DS_API_KEY.length > 0) {{
    return {{ 'X-API-Key': DS_API_KEY }};
  }}
  return {{}};
}}

async function missionCommand(cmd) {{
  const hint = document.getElementById('missionCmdHint');
  if (hint) hint.textContent = `Sending ${{cmd}}…`;

  try {{
    const r = await fetch(`/mission/command/${{cmd}}`, {{
      method: 'POST',
      cache: 'no-store',
      headers: fetchHeaders(),
    }});
    const j = await r.json();
    const ok = j.success === true;
    const txt = j.message || j.detail || (ok ? 'OK' : 'Failed');
    if (hint) {{
      hint.textContent = ok ? `✓ ${{txt}}` : `✗ ${{txt}}`;
      hint.style.color = ok ? '#136f2d' : '#a11';
      setTimeout(() => {{ hint.textContent = ''; hint.style.color = ''; }}, 4000);
    }}
  }} catch(e) {{
    if (hint) {{
      hint.textContent = `✗ ${{e}}`;
      hint.style.color = '#a11';
      setTimeout(() => {{ hint.textContent = ''; hint.style.color = ''; }}, 4000);
    }}
  }}
}}

function updateNavEnabledPill(navEnabled) {{
  const pill = document.getElementById('navEnabledPill');
  const btnStart = document.getElementById('btnMissionStart');
  const btnStop  = document.getElementById('btnMissionStop');
  if (!pill) return;
  if (navEnabled) {{
    pill.textContent = 'nav: ENABLED';
    pill.style.background = '#c8e6c9';
    pill.style.color = '#1b5e20';
    if (btnStart) {{ btnStart.style.fontWeight = '400'; btnStart.style.borderColor = ''; }}
    if (btnStop)  {{ btnStop.style.fontWeight  = '700'; btnStop.style.borderColor  = '#e53935'; btnStop.style.color = '#c62828'; }}
  }} else {{
    pill.textContent = 'nav: STOPPED';
    pill.style.background = '#ffcdd2';
    pill.style.color = '#b71c1c';
    if (btnStart) {{ btnStart.style.fontWeight = '700'; btnStart.style.borderColor = '#4caf50'; btnStart.style.color = '#1b5e20'; }}
    if (btnStop)  {{ btnStop.style.fontWeight  = '400'; btnStop.style.borderColor  = '';        btnStop.style.color  = ''; }}
  }}
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
  map = L.map('map', {{ maxZoom: 19 }}).setView([36.162, -85.501], 19);

  L.tileLayer('/tiles/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors (offline cache)'
  }}).addTo(map);

  L.control.scale({{ imperial: false, position: 'bottomleft' }}).addTo(map);

  robotMarker = L.marker([36.162, -85.501], {{
    icon: L.divIcon({{
      className: '',
      html: `<div id="robotArrow" style="
        width:0; height:0;
        border-left: 9px solid transparent;
        border-right: 9px solid transparent;
        border-bottom: 26px solid rgba(30,90,200,0.92);
        filter: drop-shadow(0 0 3px rgba(255,255,255,0.9));
        transform-origin: center 78%;
        transform: rotate(0deg);
        position: relative;
      "><div style="
        position:absolute; top:10px; left:-5px;
        width:10px; height:10px; border-radius:50%;
        background:rgba(30,90,200,0.6);
      "></div></div>`,
      iconAnchor: [9, 20],
    }}),
    zIndexOffset: 500,
    interactive: false,
  }}).addTo(map);

  trailLine = L.polyline([], {{ weight: 3 }}).addTo(map);

  accuracyCircle = L.circle([36.162, -85.501], {{
    radius: 3,
    weight: 1,
    fillOpacity: 0.08
  }}).addTo(map);
}}

// ---------------- Digital zoom (CSS scale beyond tile max) ----------------
let _dz = 1.75;
const _DZ_STEP = 0.25;
const _DZ_MIN  = 1.0;
const _DZ_MAX  = 8.0;

function _applyDz() {{
  const mapEl = document.getElementById('map');
  const badge = document.getElementById('dzoom-badge');
  mapEl.style.transform = `scale(${{_dz}})`;
  if (badge) badge.textContent = `${{_dz.toFixed(2)}}×`;
}}

function digitalZoom(dir) {{
  _dz = Math.min(_DZ_MAX, Math.max(_DZ_MIN, _dz + dir * _DZ_STEP));
  _applyDz();
}}

function digitalZoomReset() {{
  _dz = 1.0;
  _applyDz();
}}

// Scroll wheel over the map wrapper → digital zoom (Ctrl+scroll = Leaflet tile zoom)
document.getElementById('map-wrapper').addEventListener('wheel', (ev) => {{
  if (ev.ctrlKey) return;   // let Ctrl+scroll reach Leaflet
  ev.preventDefault();
  digitalZoom(ev.deltaY < 0 ? 1 : -1);
}}, {{ passive: false }});

function clearTrail() {{
  trail = [];
  if (trailLine) trailLine.setLatLngs(trail);
}}

function centerOnRobot() {{
  if (!map) return;
  if (lastLatLon) map.setView(lastLatLon, Math.max(map.getZoom(), 19));
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

  // Rotate heading arrow using compass heading (degrees, 0=North, CW)
  // Falls back to localization yaw if compass not available
  const arrowEl = document.getElementById('robotArrow');
  const hdgBadge = document.getElementById('hdgBadge');
  if (arrowEl) {{
    const hdg = safeNum((j.gps || {{}}).compass_hdg_deg);
    if (hdg !== null) {{
      arrowEl.style.transform = `rotate(${{hdg.toFixed(1)}}deg)`;
      if (hdgBadge) hdgBadge.textContent = `⌖ compass ${{hdg.toFixed(1)}}°`;
    }} else {{
      const loc = j.localization || {{}};
      const yaw_rad = safeNum(loc.yaw_rad);
      if (yaw_rad !== null) {{
        const bearing = 90.0 - (yaw_rad * 180.0 / Math.PI);
        arrowEl.style.transform = `rotate(${{bearing.toFixed(1)}}deg)`;
        if (hdgBadge) hdgBadge.textContent = `⌖ odom ${{bearing.toFixed(1)}}° (no compass)`;
      }}
    }}
  }}
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
    map.setView([lat, lon], 19);
  }}

  updateMissionOverlay(j);
  updateNavEnabledPill((j.mission || {{}}).nav_enabled === true);
}}

// ── Mission overlay ────────────────────────────────────────────────────────
// We convert map-frame XY → lat/lon using the live GPS+localization anchor.
// anchor_gps  = (gps.lat, gps.lon)          ← WGS-84 fix
// anchor_xy   = (loc.x,   loc.y)            ← same point in map frame
// Any map-frame point P = (px, py):
//   Δx = px - anchor_xy.x  (east, metres)
//   Δy = py - anchor_xy.y  (north, metres)
//   lat_P = anchor_gps.lat + Δy / 111320
//   lon_P = anchor_gps.lon + Δx / (111320 * cos(anchor_gps.lat°))

let _missionLayers = [];   // all current Leaflet layers for mission overlay

// Projection anchor — use the fixed mission origin published by
// mission_global_frame_node on /mission/origin_fix.
// This is stable: set once from the first GPS fix and never updated,
// so carrot/target positions don't drift with GPS noise.
let _anchor = null;  // {{ lat, lon }} — set from mission.origin_lat/lon

function _tryLockAnchor(mission) {{
  if (_anchor) return;  // already locked
  const lat = safeNum(mission.origin_lat);
  const lon = safeNum(mission.origin_lon);
  if (lat === null || lon === null) return;
  _anchor = {{ lat, lon, x: 0.0, y: 0.0 }};  // origin is XY (0,0) by definition
  console.log(`[mission] anchor locked from origin_fix: (${{lat.toFixed(7)}}, ${{lon.toFixed(7)}})`);
}}

function _xyToLatLon(px, py, anchorLat, anchorLon, anchorX, anchorY) {{
  const dy = py - anchorY;
  const dx = px - anchorX;
  const lat = anchorLat + dy / 111320.0;
  const lon = anchorLon + dx / (111320.0 * Math.cos(anchorLat * Math.PI / 180.0));
  return [lat, lon];
}}

function _clearMissionLayers() {{
  _missionLayers.forEach(l => map.removeLayer(l));
  _missionLayers = [];
}}

function _addLayer(layer) {{
  layer.addTo(map);
  _missionLayers.push(layer);
}}

function updateMissionOverlay(j) {{
  if (!map) return;
  _clearMissionLayers();

  const gps = j.gps || {{}};
  const mission = j.mission || {{}};

  if (!mission.present) return;

  // Lock anchor from the fixed mission origin (not live GPS)
  _tryLockAnchor(mission);
  if (!_anchor) return;

  // Badge placement: use live GPS position so it floats near the robot
  const badgeLat = safeNum(gps.lat) ?? _anchor.lat;
  const badgeLon = safeNum(gps.lon) ?? _anchor.lon;

  const toLL = (px, py) => _xyToLatLon(px, py, _anchor.lat, _anchor.lon, _anchor.x, _anchor.y);
  const acc_r = mission.acceptance_radius_m || 2.5;

  // ── Waypoints (lat/lon direct — no projection needed) ──
  const wps = mission.waypoints;
  if (Array.isArray(wps) && wps.length > 0) {{
    // Dashed route line
    const latlngs = wps.map(w => [w.lat, w.lon]);
    _addLayer(L.polyline(latlngs, {{
      color: '#1a73e8', weight: 2, dashArray: '6 4', opacity: 0.75
    }}));

    // Numbered markers
    wps.forEach((w, i) => {{
      const ll = [w.lat, w.lon];
      const isActive = (mission.waypoint_index === i);
      const isPast   = (mission.waypoint_index !== null && i < mission.waypoint_index);
      const color = isActive ? '#e67c00' : (isPast ? '#888' : '#1a73e8');

      _addLayer(L.circleMarker(ll, {{
        radius: isActive ? 9 : 6,
        color, weight: 2,
        fillColor: color, fillOpacity: isActive ? 0.9 : 0.35
      }}));

      // Acceptance radius ring on active waypoint
      if (isActive) {{
        _addLayer(L.circle(ll, {{
          radius: acc_r,
          color: '#e67c00', weight: 1.5,
          dashArray: '4 4', fill: false, opacity: 0.7
        }}));
      }}

      // Label: index + name
      const label = w.name ? `${{i}}:${{w.name}}` : String(i);
      _addLayer(L.marker(ll, {{
        icon: L.divIcon({{
          className: '',
          html: `<span style="font:bold 11px ui-monospace,monospace;
                              color:${{color}};
                              text-shadow:0 0 3px #fff,0 0 3px #fff;">${{label}}</span>`,
          iconAnchor: [-6, 6]
        }}),
        interactive: false
      }}));
    }});
  }}

  // ── Current target ──
  if (mission.target_x !== null && mission.target_x !== undefined &&
      mission.target_y !== null && mission.target_y !== undefined) {{
    const ll = toLL(mission.target_x, mission.target_y);
    _addLayer(L.circleMarker(ll, {{
      radius: 7, color: '#d93025', weight: 2,
      fillColor: '#d93025', fillOpacity: 0.2
    }}));
    // X marker via divIcon
    _addLayer(L.marker(ll, {{
      icon: L.divIcon({{
        className: '',
        html: `<span style="font:bold 14px sans-serif;color:#d93025;
                            text-shadow:0 0 3px #fff;">✕</span>`,
        iconAnchor: [7, 9]
      }}),
      interactive: false
    }}));
  }}

  // ── Carrot target ──
  const cx = safeNum(mission.carrot_x);
  const cy = safeNum(mission.carrot_y);
  if (cx !== null && cy !== null) {{
    const ll = toLL(cx, cy);
    _addLayer(L.circleMarker(ll, {{
      radius: 7, color: '#7b2d8b', weight: 2.5,
      fillColor: '#ce93d8', fillOpacity: 0.85
    }}));
    _addLayer(L.marker(ll, {{
      icon: L.divIcon({{
        className: '',
        html: `<span style="font:bold 12px sans-serif;color:#7b2d8b;
                            text-shadow:0 0 3px #fff;">🥕</span>`,
        iconAnchor: [8, 8]
      }}),
      interactive: false
    }}));
  }}

  // ── Mission status badge ──
  const idx   = mission.waypoint_index !== null && mission.waypoint_index !== undefined ? mission.waypoint_index : '—';
  const done  = mission.mission_complete ? ' ✓ COMPLETE' : '';
  const total = Array.isArray(wps) ? wps.length : '?';
  const carrotStr = (cx !== null && cy !== null) ? `${{cx.toFixed(1)}},${{cy.toFixed(1)}}` : 'none';
  const wpStr = Array.isArray(wps) ? (wps.length === 0 ? 'empty[]' : `${{wps.length}} loaded`) : 'null';
  const anchorStr = _anchor
    ? `${{_anchor.lat.toFixed(5)}},${{_anchor.lon.toFixed(5)}}`
    : 'waiting…';
  console.log('[mission]', JSON.stringify({{
    present: mission.present,
    origin: anchorStr,
    waypoints: wpStr,
    wp_index: idx,
    carrot: carrotStr,
  }}));
  _addLayer(L.marker([badgeLat, badgeLon], {{
    icon: L.divIcon({{
      className: '',
      html: `<div style="background:rgba(255,255,255,0.88);border:1px solid #ccc;
                         border-radius:6px;padding:2px 7px;font:11px ui-monospace,monospace;
                         white-space:nowrap;pointer-events:none;">
               WP ${{idx}}/${{total}} (${{wpStr}})${{done}} · 🥕(${{carrotStr}}) · ⚓(${{anchorStr}})
             </div>`,
      iconAnchor: [-8, -8]
    }}),
    interactive: false,
    zIndexOffset: 1000
  }}));
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
  if (map) map.invalidateSize();
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

  // ── Battery voltage ──
  // 10S LiPo: max ~42.0 V (4.2V/cell), nominal 37V, cutoff ~33.0 V
  const BATT_MAX = 42.0;
  const BATT_MIN = 33.0;
  const vL = safeNum((j.vesc_left  || {{}}).input_voltage_v);
  const vR = safeNum((j.vesc_right || {{}}).input_voltage_v);
  const vAvg = (vL !== null && vR !== null) ? (vL + vR) / 2
             : (vL !== null ? vL : (vR !== null ? vR : null));

  const fill  = document.getElementById('battFill');
  const volts = document.getElementById('battVolts');
  if (vAvg !== null) {{
    const pct = Math.max(0, Math.min(100, (vAvg - BATT_MIN) / (BATT_MAX - BATT_MIN) * 100));
    fill.style.width = pct + '%';
    fill.style.background = pct > 50 ? '#4caf50' : pct > 20 ? '#ff9800' : '#f44336';
    const lStr = vL !== null ? vL.toFixed(1) : '—';
    const rStr = vR !== null ? vR.toFixed(1) : '—';
    volts.textContent = vAvg.toFixed(1) + ' V';
    volts.title = `L: ${{lStr}} V  R: ${{rStr}} V`;
    volts.className = 'battery-voltage ' + (pct > 50 ? 'ok' : pct > 20 ? 'warn' : 'bad');
  }} else {{
    fill.style.width = '0%';
    volts.textContent = '—';
    volts.className = 'battery-voltage muted';
  }}
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

// ══════════════════════════════════════════════
// WAYPOINT EDITOR
// ══════════════════════════════════════════════
let _wpEditorMap = null;
let _wpEditorWaypoints = [];   // [{{lat, lon, name}}]  — working copy
let _wpEditorMode = 'add';     // 'add' | 'pan'
let _wpEditorLayers = [];
let _wpPreviewMode = false;    // true = loaded from file, not yet sent

function openWpEditor() {{
  const overlay = document.getElementById('wpEditorOverlay');
  overlay.classList.add('open');

  // Clone current mission waypoints into editor
  const currentWps = (statusData && statusData.mission && statusData.mission.waypoints)
    ? statusData.mission.waypoints.map(w => ({{lat: w.lat, lon: w.lon, name: w.name}}))
    : [];
  _wpEditorWaypoints = currentWps;
  _wpPreviewMode = false;
  document.getElementById('wpPreviewBanner').style.display = 'none';

  // Init map (once)
  if (!_wpEditorMap) {{
    _wpEditorMap = L.map('wpEditorMap', {{ zoomControl: true }});
    L.tileLayer('/tiles/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 22, minZoom: 10,
      attribution: '© OpenStreetMap contributors'
    }}).addTo(_wpEditorMap);

    // Try OSM fallback
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19, attribution: '© OpenStreetMap'
    }}).addTo(_wpEditorMap);

    _wpEditorMap.on('click', onEditorMapClick);
  }}

  // Centre on current GPS or last known waypoint
  const gps = statusData && statusData.gps;
  const lat = (gps && gps.lat) ? gps.lat : (_wpEditorWaypoints.length ? _wpEditorWaypoints[0].lat : 36.1756);
  const lon = (gps && gps.lon) ? gps.lon : (_wpEditorWaypoints.length ? _wpEditorWaypoints[0].lon : -85.5085);
  _wpEditorMap.setView([lat, lon], 18);
  setTimeout(() => _wpEditorMap.invalidateSize(), 50);

  renderWpEditorList();
  renderWpEditorMapMarkers();
}}

function closeWpEditor() {{
  document.getElementById('wpEditorOverlay').classList.remove('open');
}}

function setWpMode(mode) {{
  _wpEditorMode = mode;
  document.getElementById('btnModeAdd').classList.toggle('active', mode === 'add');
  document.getElementById('btnModePan').classList.toggle('active', mode === 'pan');
  document.getElementById('wpEditorHint').textContent =
    mode === 'add' ? 'Click on the map to place a waypoint' : 'Pan mode — click does not add waypoints';
  if (_wpEditorMap) {{
    _wpEditorMap.dragging.enable();
  }}
}}

function onEditorMapClick(e) {{
  if (_wpEditorMode !== 'add') return;
  const name = `wp_${{_wpEditorWaypoints.length}}`;
  _wpEditorWaypoints.push({{ lat: e.latlng.lat, lon: e.latlng.lng, name }});
  renderWpEditorList();
  renderWpEditorMapMarkers();
}}

function renderWpEditorMapMarkers() {{
  if (!_wpEditorMap) return;
  _wpEditorLayers.forEach(l => _wpEditorMap.removeLayer(l));
  _wpEditorLayers = [];

  if (_wpEditorWaypoints.length > 1) {{
    const lls = _wpEditorWaypoints.map(w => [w.lat, w.lon]);
    const pl = L.polyline(lls, {{ color: '#1a73e8', weight: 2, dashArray: '6 4', opacity: 0.75 }});
    pl.addTo(_wpEditorMap);
    _wpEditorLayers.push(pl);
  }}

  _wpEditorWaypoints.forEach((w, i) => {{
    const color = '#1a73e8';
    const cm = L.circleMarker([w.lat, w.lon], {{
      radius: 7, color, weight: 2, fillColor: color, fillOpacity: 0.35
    }}).addTo(_wpEditorMap);
    _wpEditorLayers.push(cm);

    const lm = L.marker([w.lat, w.lon], {{
      icon: L.divIcon({{
        className: '',
        html: `<span style="font:bold 11px ui-monospace,monospace;color:${{color}};
                             text-shadow:0 0 3px #fff,0 0 3px #fff;">${{i}}:${{w.name}}</span>`,
        iconAnchor: [-6, 6]
      }}),
      interactive: false
    }}).addTo(_wpEditorMap);
    _wpEditorLayers.push(lm);
  }});
}}

function renderWpEditorList() {{
  const ul = document.getElementById('wpList');
  ul.innerHTML = '';
  _wpEditorWaypoints.forEach((w, i) => {{
    const li = document.createElement('li');
    li.dataset.idx = i;
    li.draggable = true;

    li.innerHTML = `
      <span class="wp-idx">${{i}}</span>
      <input type="text" value="${{escHtml(w.name)}}" placeholder="name"
             onchange="_wpEditorWaypoints[${{i}}].name=this.value;renderWpEditorMapMarkers()"/>
      <span class="wp-coords">${{w.lat.toFixed(6)}},&nbsp;${{w.lon.toFixed(6)}}</span>
      <span class="wp-del" onclick="removeWp(${{i}})" title="Remove">✕</span>
    `;

    li.addEventListener('dragstart', e => {{ e.dataTransfer.setData('text/plain', i); }});
    li.addEventListener('dragover', e => {{ e.preventDefault(); li.classList.add('drag-over'); }});
    li.addEventListener('dragleave', () => li.classList.remove('drag-over'));
    li.addEventListener('drop', e => {{
      e.preventDefault();
      li.classList.remove('drag-over');
      const from = parseInt(e.dataTransfer.getData('text/plain'));
      const to = i;
      if (from === to) return;
      const moved = _wpEditorWaypoints.splice(from, 1)[0];
      _wpEditorWaypoints.splice(to, 0, moved);
      renderWpEditorList();
      renderWpEditorMapMarkers();
    }});

    ul.appendChild(li);
  }});
}}

function removeWp(i) {{
  _wpEditorWaypoints.splice(i, 1);
  renderWpEditorList();
  renderWpEditorMapMarkers();
}}

function clearAllWaypoints() {{
  if (!confirm('Clear all waypoints in the editor?')) return;
  _wpEditorWaypoints = [];
  renderWpEditorList();
  renderWpEditorMapMarkers();
}}

async function confirmSendWaypoints() {{
  if (_wpEditorWaypoints.length === 0) {{
    alert('No waypoints to send.');
    return;
  }}
  if (!confirm(`Send ${{_wpEditorWaypoints.length}} waypoint(s) to the robot? This will replace the current mission.`)) return;
  try {{
    const r = await fetch('/mission/waypoints', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', ...fetchHeaders() }},
      body: JSON.stringify(_wpEditorWaypoints)
    }});
    const data = await r.json();
    if (!r.ok) {{
      alert('Failed to send waypoints: ' + (data.detail || JSON.stringify(data)));
      return;
    }}
    _wpPreviewMode = false;
    document.getElementById('wpPreviewBanner').style.display = 'none';
    document.getElementById('wpEditorHint').textContent =
      `✓ ${{_wpEditorWaypoints.length}} waypoints sent to robot.`;
    setTimeout(() => closeWpEditor(), 800);
  }} catch(e) {{
    alert('Error sending waypoints: ' + e);
  }}
}}

async function saveWaypointsToRobot() {{
  if (_wpEditorWaypoints.length === 0) {{
    alert('No waypoints to save.');
    return;
  }}
  try {{
    const r1 = await fetch('/mission/waypoints', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', ...fetchHeaders() }},
      body: JSON.stringify(_wpEditorWaypoints)
    }});
    const d1 = await r1.json();
    if (!r1.ok) {{ alert('Send failed: ' + (d1.detail || JSON.stringify(d1))); return; }}

    const r2 = await fetch('/mission/save_waypoints', {{
      method: 'POST', headers: fetchHeaders()
    }});
    const d2 = await r2.json();
    if (!r2.ok) {{ alert('Save failed: ' + (d2.detail || JSON.stringify(d2))); return; }}
    alert(d2.success ? '✓ ' + d2.message : 'Save failed: ' + d2.message);
  }} catch(e) {{
    alert('Error: ' + e);
  }}
}}

async function exportWaypoints() {{
  try {{
    const r = await fetch('/mission/export_waypoints', {{ headers: fetchHeaders() }});
    if (!r.ok) throw new Error(`HTTP ${{r.status}}`);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'waypoints.yaml'; a.click();
    URL.revokeObjectURL(url);
  }} catch(e) {{
    alert('Export failed: ' + e);
  }}
}}

function loadWpFile() {{
  document.getElementById('wpFileInput').click();
}}

function onWpFileSelected(event) {{
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {{
    try {{
      const text = e.target.result;
      let wps = [];

      if (file.name.endsWith('.json')) {{
        // JSON: [{{"lat":...,"lon":...,"name":...}}]
        const data = JSON.parse(text);
        wps = data.map((w, i) => ({{
          lat: parseFloat(w.lat || w.latitude),
          lon: parseFloat(w.lon || w.longitude),
          name: w.name || `wp_${{i}}`
        }}));
      }} else {{
        // YAML: simple line-by-line parser for the standard format
        wps = parseWaypointsYaml(text);
      }}

      if (wps.length === 0) {{ alert('No valid waypoints found in file.'); return; }}

      _wpEditorWaypoints = wps;
      _wpPreviewMode = true;
      document.getElementById('wpPreviewBanner').style.display = 'block';
      renderWpEditorList();
      renderWpEditorMapMarkers();

      // Fit map to loaded waypoints
      if (_wpEditorMap && wps.length > 0) {{
        const bounds = L.latLngBounds(wps.map(w => [w.lat, w.lon]));
        _wpEditorMap.fitBounds(bounds, {{ padding: [40, 40] }});
      }}
    }} catch(err) {{
      alert('Failed to parse file: ' + err);
    }}
  }};
  reader.readAsText(file);
  event.target.value = '';
}}

function cancelPreview() {{
  // Revert to current mission waypoints
  const currentWps = (statusData && statusData.mission && statusData.mission.waypoints)
    ? statusData.mission.waypoints.map(w => ({{lat: w.lat, lon: w.lon, name: w.name}}))
    : [];
  _wpEditorWaypoints = currentWps;
  _wpPreviewMode = false;
  document.getElementById('wpPreviewBanner').style.display = 'none';
  renderWpEditorList();
  renderWpEditorMapMarkers();
}}

function parseWaypointsYaml(text) {{
  // Minimal YAML parser for the known format:
  //   waypoints:
  //     - name: start
  //       latitude: 36.1234
  //       longitude: -85.5678
  //       altitude: 0.0
  const wps = [];
  let current = null;
  for (const raw of text.split('\\n')) {{
    const line = raw.trim();
    if (line.startsWith('- ') || line === '-') {{
      if (current) wps.push(current);
      current = {{}};
      const rest = line.slice(2).trim();
      if (rest) parseYamlKv(current, rest);
    }} else if (current && line.includes(':')) {{
      parseYamlKv(current, line);
    }}
  }}
  if (current && (current.latitude || current.lat)) wps.push(current);

  return wps
    .filter(w => (w.latitude || w.lat) && (w.longitude || w.lon))
    .map((w, i) => ({{
      lat: parseFloat(w.latitude || w.lat),
      lon: parseFloat(w.longitude || w.lon),
      name: w.name || `wp_${{i}}`
    }}));
}}

function parseYamlKv(obj, line) {{
  const idx = line.indexOf(':');
  if (idx < 0) return;
  const k = line.slice(0, idx).trim();
  const v = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
  obj[k] = v;
}}

function escHtml(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// ══════════════════════════════════════════════
// END WAYPOINT EDITOR
// ══════════════════════════════════════════════

initGpsMap();
resizeCanvas();
fetchCostmap();
refresh();
setInterval(refresh, 1000);
setInterval(fetchCostmap, 1000);

// Fix: tell Leaflet the true container size after the flex layout has painted.
// Without this, Leaflet measures #map at 0px height and tile layers break on zoom.
setTimeout(() => {{ if (map) map.invalidateSize(); }}, 0);
requestAnimationFrame(() => {{ if (map) map.invalidateSize(); }});
</script>

</body>
</html>
"""