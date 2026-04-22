#ifndef WEB_UI_H
#define WEB_UI_H

// ---------------------------------------------------------------------------
// ManhaCam Web UI — inlined into PROGMEM.
//
// Source files for development:
//   index.html   — page structure
//   styles.css   — stylesheet
//   scripts.js   — application logic
//
// This file is the compiled single-page version with CSS and JS inlined.
// ---------------------------------------------------------------------------

static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ManhaCam</title>
<style>
:root {
  --bg:#0A0428;--surface:#131030;--border:#2C2D53;--text:#B0CDFD;
  --muted:#727797;--accent:#B0CDFD;--danger:#F44336;--success:#69F0AE;
  --subtle:#8295C0;--sidebar-w:300px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:linear-gradient(180deg,#050311 0%,#0A0428 100%);background-attachment:fixed;color:var(--text);min-height:100vh}
.header{padding:1.2rem 1.5rem 0}
.header h1{font-size:1.5rem;font-weight:700;letter-spacing:1px}
.header .subtitle{font-size:.8rem;color:var(--muted);margin-top:.2rem;letter-spacing:.5px}
.tab-bar{display:flex;gap:0;padding:0 1.5rem;border-bottom:1px solid var(--border);margin-top:1rem}
.tab-btn{background:none;border:none;color:var(--muted);font-size:.82rem;font-weight:600;letter-spacing:.5px;text-transform:uppercase;padding:.6rem 1.2rem;cursor:pointer;position:relative;transition:color .2s;font-family:inherit}
.tab-btn:hover{color:var(--text)}.tab-btn.active{color:var(--text)}
.tab-btn.active::after{content:'';position:absolute;bottom:-1px;left:.6rem;right:.6rem;height:2px;background:var(--accent);border-radius:2px 2px 0 0}
.tab-btn.settings-tab{display:inline-block}
@media(min-width:860px){.tab-btn.settings-tab{display:none}}
@media(max-width:859px){
  .tab-bar{position:fixed;bottom:0;left:0;right:0;z-index:50;background:var(--surface);border-top:1px solid var(--border);border-bottom:none;margin:0;padding:0;justify-content:stretch}
  .tab-btn{flex:1;text-align:center;padding:.75rem .5rem;font-size:.72rem}
  .tab-btn.active::after{top:0;bottom:auto;border-radius:0 0 2px 2px}
  .main-content{padding-bottom:4rem}
}
.main-wrap{display:flex;min-height:calc(100vh - 120px)}
.main-content{flex:1;min-width:0;padding:1rem 1.5rem 2rem}
.tab-panel{display:none}.tab-panel.active{display:block}
.sidebar{display:none;width:var(--sidebar-w);min-width:var(--sidebar-w);border-left:1px solid var(--border);background:rgba(10,4,40,.6);padding:1rem;overflow-y:auto;max-height:calc(100vh - 120px);position:sticky;top:0}
@media(min-width:860px){.sidebar{display:block}#tab-settings{display:none!important}}
.sidebar h2{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--subtle);margin-bottom:.8rem}
#status{padding:.5rem .8rem;border-radius:6px;font-size:.8rem;letter-spacing:.3px;margin-bottom:1rem;display:none}
#status.info{display:block;background:rgba(176,205,253,.08);border:1px solid var(--border);color:var(--subtle)}
#status.ok{display:block;background:rgba(105,240,174,.08);border:1px solid rgba(105,240,174,.3);color:var(--success)}
#status.err{display:block;background:rgba(244,67,54,.08);border:1px solid rgba(244,67,54,.3);color:var(--danger)}
button{font-family:inherit;font-size:.8rem;font-weight:600;letter-spacing:.5px;padding:.5rem 1rem;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text);cursor:pointer;transition:all .15s}
button:hover{border-color:var(--accent)}button:active{transform:scale(.97)}
.btn-accent{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.btn-accent:hover{background:#c4dafd;border-color:#c4dafd}
.btn-accent.unsaved{animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
.btn-danger{background:transparent;color:var(--danger);border-color:var(--danger)}
.btn-danger:hover{background:rgba(244,67,54,.1)}
.btn-sm{font-size:.72rem;padding:.35rem .7rem}
.btn-outline{background:transparent;color:var(--text);border-color:var(--border)}
.toolbar{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem;align-items:center}
.toolbar .sort-toggle{margin-left:auto}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.75rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;transition:border-color .2s}
.card:hover{border-color:var(--accent)}
.card img{width:100%;aspect-ratio:4/3;object-fit:cover;cursor:pointer;background:#080218}
.card .info{padding:.5rem .65rem;display:flex;justify-content:space-between;align-items:center}
.card .fname{font-size:.72rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%;letter-spacing:.3px}
.card .fsize{font-size:.68rem;color:var(--muted)}
.empty-state{text-align:center;padding:3rem 1rem;color:var(--muted);font-size:.85rem;letter-spacing:.5px}
.lightbox{display:none;position:fixed;inset:0;background:rgba(5,3,17,.95);z-index:100;justify-content:center;align-items:center;flex-direction:column;padding:1rem}
.lightbox.active{display:flex}
.lightbox img{max-width:95vw;max-height:80vh;border-radius:6px}
.lightbox .lb-bar{margin-top:.8rem;display:flex;gap:.5rem;align-items:center}
.lightbox .lb-name{color:var(--muted);font-size:.8rem;letter-spacing:.3px;margin-right:.5rem}
.preset-bar{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.8rem}
.preset-bar button.active{border-color:var(--accent);color:var(--accent);background:rgba(176,205,253,.08)}
.settings-grid{display:flex;flex-direction:column;gap:.6rem}
#tab-settings .settings-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.7rem 1rem}
.setting-item{display:flex;flex-direction:column;gap:.2rem}
.setting-item label{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.setting-item select,.setting-item input[type=range]{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:.35rem;font-size:.78rem;font-family:inherit}
.setting-item select:focus,.setting-item input:focus{outline:none;border-color:var(--accent)}
.setting-item input[type=range]{padding:.2rem 0;accent-color:var(--accent)}
.range-val{font-size:.68rem;color:var(--accent);float:right;font-weight:400}
.toggle-section{margin-top:.8rem}
.toggle-section>label.section-label{display:block;font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:.4rem}
.toggle-row{display:flex;flex-wrap:wrap;gap:.5rem .8rem}
.toggle-row label{display:flex;align-items:center;gap:.25rem;font-size:.75rem;color:var(--text);cursor:pointer;letter-spacing:.3px}
.toggle-row input[type=checkbox]{accent-color:var(--accent);width:13px;height:13px}
.settings-actions{margin-top:1rem;display:flex;flex-wrap:wrap;gap:.4rem;border-top:1px solid var(--border);padding-top:.8rem}
.settings-actions button{flex:1;min-width:0;font-size:.72rem;padding:.45rem .5rem}
.sys-section{margin-bottom:1.5rem}
.sys-section h3{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--subtle);margin-bottom:.6rem}
.sys-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.log-terminal{font-family:'Courier New',monospace;font-size:.73rem;color:var(--subtle);padding:.7rem;height:200px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;line-height:1.5;background:#050311}
.log-bar{display:flex;gap:.4rem;padding:.4rem .7rem;border-top:1px solid var(--border);background:var(--surface)}
.ota-body{padding:1rem}
.ota-row{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap}
.ota-row input[type=file]{font-size:.78rem;color:var(--text)}
.ota-row input[type=file]::file-selector-button{font-family:inherit;font-size:.75rem;font-weight:600;padding:.4rem .8rem;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text);cursor:pointer;margin-right:.5rem;letter-spacing:.3px}
.ota-row input[type=file]::file-selector-button:hover{border-color:var(--accent)}
.progress-track{margin-top:.8rem;background:var(--border);border-radius:4px;height:5px;overflow:hidden;display:none}
.progress-fill{background:var(--accent);height:100%;width:0%;transition:width .3s;border-radius:4px}
.ota-status{font-size:.72rem;color:var(--muted);margin-top:.4rem;letter-spacing:.3px}
.info-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.6rem}
.info-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:.8rem}
.info-card .info-label{font-size:.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:.3rem}
.info-card .info-value{font-size:1rem;font-weight:700;color:#fff}
.info-card .info-value.ok{color:var(--success)}
.info-card .info-value.warn{color:#FFD740}
@media(max-width:600px){
  .header{padding:1rem 1rem 0}.main-content{padding:.8rem 1rem 4rem}
  .gallery{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}
  #tab-settings .settings-grid{grid-template-columns:1fr}
  .info-grid{grid-template-columns:1fr 1fr}
}
@media(min-width:1200px){:root{--sidebar-w:320px}}
</style>
</head>
<body>

<div class="header">
  <h1>ManhaCam</h1>
  <p class="subtitle"><span id="img-count">0</span> images</p>
</div>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('gallery',this)">Gallery</button>
  <button class="tab-btn settings-tab" onclick="switchTab('settings',this)">Settings</button>
  <button class="tab-btn" onclick="switchTab('system',this)">System</button>
</div>

<div class="main-wrap">
  <div class="main-content">
    <div id="status"></div>

    <div class="tab-panel active" id="tab-gallery">
      <div class="toolbar">
        <button class="btn-accent" onclick="capture()">Capture</button>
        <button class="btn-outline" onclick="refresh()">Refresh</button>
        <button class="btn-danger" onclick="clearAll()">Clear SD</button>
        <button class="btn-outline sort-toggle" id="sort-toggle" data-sort="num-desc" onclick="toggleSort()">Name &#8595;</button>
      </div>
      <div id="gallery" class="gallery"></div>
    </div>

    <div class="tab-panel" id="tab-settings"></div>

    <div class="tab-panel" id="tab-system">
      <div class="sys-section">
        <h3>Status</h3>
        <div class="info-grid">
          <div class="info-card"><div class="info-label">SD Card</div><div class="info-value ok" id="sys-sd">&mdash;</div></div>
          <div class="info-card"><div class="info-label">Free Space</div><div class="info-value" id="sys-free">&mdash;</div></div>
          <div class="info-card"><div class="info-label">Images</div><div class="info-value" id="sys-images">&mdash;</div></div>
          <div class="info-card"><div class="info-label">Sensor</div><div class="info-value" id="sys-sensor">&mdash;</div></div>
        </div>
      </div>
      <div class="sys-section">
        <h3>Firmware Update</h3>
        <div class="sys-card"><div class="ota-body">
          <div class="ota-row">
            <input type="file" id="ota-file" accept=".bin">
            <button class="btn-accent" id="ota-btn" onclick="otaClick()">Upload &amp; Flash</button>
          </div>
          <div class="progress-track" id="ota-progress"><div class="progress-fill" id="ota-bar"></div></div>
          <div class="ota-status" id="ota-status"></div>
        </div></div>
      </div>
      <div class="sys-section">
        <h3>Log Console</h3>
        <div class="sys-card">
          <div class="log-terminal" id="log-term"></div>
          <div class="log-bar">
            <button class="btn-sm" onclick="clearLog()">Clear</button>
            <button class="btn-sm" id="log-pause-btn" onclick="toggleLogPause()">Pause</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <aside class="sidebar" id="sidebar-host">
    <h2>Camera Settings</h2>
    <div id="settings-panel">
      <div class="preset-bar"></div>
      <div class="settings-grid">
        <div class="setting-item"><label>Resolution</label><select id="s-framesize"></select></div>
        <div class="setting-item"><label>JPEG Quality <span class="range-val" id="v-quality"></span></label><input type="range" id="s-quality" min="10" max="63" step="1"></div>
        <div class="setting-item"><label>Brightness <span class="range-val" id="v-brightness"></span></label><input type="range" id="s-brightness" min="-2" max="2" step="1"></div>
        <div class="setting-item"><label>Contrast <span class="range-val" id="v-contrast"></span></label><input type="range" id="s-contrast" min="-2" max="2" step="1"></div>
        <div class="setting-item"><label>Saturation <span class="range-val" id="v-saturation"></span></label><input type="range" id="s-saturation" min="-2" max="2" step="1"></div>
        <div class="setting-item"><label>AE Level <span class="range-val" id="v-ae_level"></span></label><input type="range" id="s-ae_level" min="-2" max="2" step="1"></div>
        <div class="setting-item"><label>AGC Gain <span class="range-val" id="v-agc_gain"></span></label><input type="range" id="s-agc_gain" min="0" max="30" step="1"></div>
        <div class="setting-item"><label>Gain Ceiling</label><select id="s-gainceiling"><option value="0">2x</option><option value="1">4x</option><option value="2">8x</option><option value="3">16x</option><option value="4">32x</option><option value="5">64x</option><option value="6">128x</option></select></div>
        <div class="setting-item"><label>White Balance</label><select id="s-wb_mode"><option value="0">Auto</option><option value="1">Sunny</option><option value="2">Cloudy</option><option value="3">Office</option><option value="4">Home</option></select></div>
        <div class="setting-item"><label>Special Effect</label><select id="s-special_effect"><option value="0">None</option><option value="1">Negative</option><option value="2">Grayscale</option><option value="3">Red Tint</option><option value="4">Green Tint</option><option value="5">Blue Tint</option><option value="6">Sepia</option></select></div>

      </div>
      <div class="toggle-section">
        <label class="section-label">Toggles</label>
        <div class="toggle-row">
          <label><input type="checkbox" id="s-awb"> AWB</label>
          <label><input type="checkbox" id="s-awb_gain"> AWB Gain</label>
          <label><input type="checkbox" id="s-aec"> AEC</label>
          <label><input type="checkbox" id="s-aec2"> AEC2 (DSP)</label>
          <label><input type="checkbox" id="s-agc"> AGC</label>
          <label><input type="checkbox" id="s-bpc"> BPC</label>
          <label><input type="checkbox" id="s-wpc"> WPC</label>
          <label><input type="checkbox" id="s-raw_gma"> Gamma</label>
          <label><input type="checkbox" id="s-lenc"> Lens Corr</label>
          <label><input type="checkbox" id="s-hmirror"> H-Mirror</label>
          <label><input type="checkbox" id="s-vflip"> V-Flip</label>
        </div>
      </div>
      <div class="settings-actions">
        <button class="btn-accent" id="btn-apply" onclick="applySettings()">Apply &amp; Save</button>
        <button class="btn-outline" onclick="loadSettings()">Reset</button>
        <button class="btn-danger" id="btn-reset" onclick="factoryReset()">Factory Reset</button>
      </div>
    </div>
  </aside>
</div>

<div class="lightbox" id="lb" onclick="closeLb(event)">
  <img id="lb-img" src="">
  <div class="lb-bar">
    <span class="lb-name" id="lb-name"></span>
    <a id="lb-dl" download><button class="btn-sm">Download</button></a>
    <button class="btn-sm btn-danger" id="lb-del" onclick="deleteCurrent(event)">Delete</button>
    <button class="btn-sm" onclick="closeLb(event,true)">Close</button>
  </div>
</div>

<script>
let panel=document.getElementById('settings-panel');
let sidebarHost=document.getElementById('sidebar-host');
let tabHost=document.getElementById('tab-settings');
let heading=sidebarHost.querySelector('h2');
let lastWide=null;
function relocateSettings(){
  let wide=window.innerWidth>=860;
  if(wide===lastWide)return;
  lastWide=wide;
  if(wide)heading.after(panel);else tabHost.appendChild(panel);
}
relocateSettings();
window.addEventListener('resize',relocateSettings);
</script>

<script>
let files=[];
let sortedFiles=[];
let currentFile='';
let presets=[];
let currentSettings={};
const PAGE_SIZE=20;
let visibleCount=PAGE_SIZE;
let logOffset=0,logPaused=false,logTimer=null,logLines=0;
const RANGE_FIELDS=['quality','brightness','contrast','saturation','ae_level','agc_gain'];
const SELECT_FIELDS=['framesize','gainceiling','wb_mode','special_effect'];
const TOGGLE_FIELDS=['awb','awb_gain','aec','aec2','agc','bpc','wpc','raw_gma','lenc','hmirror','vflip'];

function status(msg,cls){let el=document.getElementById('status');el.textContent=msg;el.className=cls||'info'}
async function apiFetch(path,opts){try{let r=await fetch(path,opts||{});if(!r.ok)throw new Error(await r.text()||r.statusText);return r}catch(e){status('Error: '+e.message,'err');throw e}}
function formatSize(b){if(b<1024)return b+' B';if(b<1048576)return(b/1024).toFixed(1)+' KB';return(b/1048576).toFixed(1)+' MB'}

function switchTab(tabId,btn){
  document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active')});
  document.getElementById('tab-'+tabId).classList.add('active');
  btn.classList.add('active');
  if(tabId==='system'){if(!logTimer)logTimer=setInterval(pollLogs,2000);pollLogs()}
  else if(logTimer){clearInterval(logTimer);logTimer=null}
}

function renderCard(f){
  let esc=f.name.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
  return '<div class="card"><img src="/api/image?name='+encodeURIComponent(f.name)+'" loading="lazy" data-name="'+esc+'" onclick="openLb(this.dataset.name)"><div class="info"><span class="fname" title="'+esc+'">'+esc+'</span><span class="fsize">'+formatSize(f.size)+'</span></div></div>';
}
function render(){
  let g=document.getElementById('gallery');
  if(!files.length){g.innerHTML='<div class="empty-state">No images on SD card.</div>';return}
  
  let sort=document.getElementById('sort-toggle').dataset.sort;
  sortedFiles=[...files];
  sortedFiles.sort(function(a,b){
    let dir=sort.endsWith('-desc')?-1:1;
    let na=parseInt((a.name.match(/img_(\d+)/)||[0,0])[1]);
    let nb=parseInt((b.name.match(/img_(\d+)/)||[0,0])[1]);
    return (na-nb)*dir;
  });
  
  let showing=sortedFiles.slice(0,visibleCount);
  let html=showing.map(renderCard).join('');
  if(visibleCount<sortedFiles.length)html+='<div class="empty-state"><button onclick="loadMore()">Load more ('+(sortedFiles.length-visibleCount)+' remaining)</button></div>';
  g.innerHTML=html;
}
function loadMore(){visibleCount+=PAGE_SIZE;render()}
function toggleSort(){let b=document.getElementById('sort-toggle');let d=b.dataset.sort==='num-desc'?'num-asc':'num-desc';b.dataset.sort=d;b.innerHTML='Name '+(d==='num-desc'?'&#8595;':'&#8593;');render()}
async function refresh(){
  status('Loading...','info');
  try{let r=await apiFetch('/api/images');let data=await r.json();files=data.files||[];sortedFiles=[];visibleCount=PAGE_SIZE;render();document.getElementById('img-count').textContent=files.length;status(files.length+' image(s) on SD card','ok')}catch(e){}
}
async function capture(){status('Capturing...','info');try{let r=await apiFetch('/api/capture',{method:'POST'});let data=await r.json();status('Saved: '+(data.filename||'ok'),'ok');await refresh()}catch(e){}}
async function deleteFile(name){status('Deleting '+name+'...','info');try{await apiFetch('/api/image?name='+encodeURIComponent(name),{method:'DELETE'});status('Deleted: '+name,'ok');await refresh()}catch(e){}}
async function clearAll(){if(!confirm('Delete ALL images from SD card?'))return;status('Clearing SD card...','info');try{await apiFetch('/api/images',{method:'DELETE'});status('SD card cleared.','ok');await refresh()}catch(e){}}

function openLb(name){currentFile=name;let url='/api/image?name='+encodeURIComponent(name);document.getElementById('lb-img').src=url;document.getElementById('lb-name').textContent=name;let dl=document.getElementById('lb-dl');dl.href=url;dl.download=name;document.getElementById('lb').classList.add('active')}
function closeLb(e,force){if(force||e.target===document.getElementById('lb'))document.getElementById('lb').classList.remove('active')}
function deleteCurrent(e){e.stopPropagation();if(confirm('Delete '+currentFile+'?')){closeLb(null,true);deleteFile(currentFile)}}
function navigateLb(dir){let idx=sortedFiles.findIndex(function(f){return f.name===currentFile});if(idx<0)return;let next=idx+dir;if(next>=0&&next<sortedFiles.length)openLb(sortedFiles[next].name)}
document.addEventListener('keydown',function(e){if(!document.getElementById('lb').classList.contains('active'))return;if(e.key==='Escape')closeLb(null,true);else if(e.key==='ArrowLeft')navigateLb(-1);else if(e.key==='ArrowRight')navigateLb(1)});

function settingsToUI(s){
  SELECT_FIELDS.forEach(function(k){document.getElementById('s-'+k).value=s[k]});
  RANGE_FIELDS.forEach(function(k){let el=document.getElementById('s-'+k);el.value=s[k];let vEl=document.getElementById('v-'+k);if(vEl)vEl.textContent=s[k]});
  TOGGLE_FIELDS.forEach(function(k){document.getElementById('s-'+k).checked=!!s[k]});
}
function uiToSettings(){let s={};SELECT_FIELDS.forEach(function(k){s[k]=parseInt(document.getElementById('s-'+k).value)});RANGE_FIELDS.forEach(function(k){s[k]=parseInt(document.getElementById('s-'+k).value)});TOGGLE_FIELDS.forEach(function(k){s[k]=document.getElementById('s-'+k).checked?1:0});return s}
function markUnsaved(){let ui=uiToSettings();let changed=Object.keys(ui).some(function(k){return ui[k]!==currentSettings[k]});document.getElementById('btn-apply').classList.toggle('unsaved',changed)}
function selectPreset(idx){settingsToUI(presets[idx].settings);highlightPreset();markUnsaved()}
function highlightPreset(){let ui=uiToSettings();document.querySelectorAll('.preset-bar button[data-pi]').forEach(function(btn){let pi=parseInt(btn.dataset.pi);let ps=presets[pi].settings;let match=Object.keys(ui).every(function(k){return ui[k]===ps[k]});btn.classList.toggle('active',match)})}
async function applySettings(){let btn=document.getElementById('btn-apply');btn.disabled=true;let s=uiToSettings();status('Applying settings...','info');try{let r=await apiFetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});currentSettings=await r.json();settingsToUI(currentSettings);highlightPreset();status('Settings applied & saved to flash','ok')}catch(e){}btn.disabled=false;btn.classList.remove('unsaved')}
async function factoryReset(){if(!confirm('Reset all camera settings to factory defaults?'))return;let btn=document.getElementById('btn-reset');btn.disabled=true;status('Resetting...','info');try{let r=await apiFetch('/api/settings/reset',{method:'POST'});currentSettings=await r.json();settingsToUI(currentSettings);highlightPreset();status('Factory reset complete','ok')}catch(e){}btn.disabled=false}
async function loadSettings(){try{let r=await apiFetch('/api/settings');currentSettings=await r.json();settingsToUI(currentSettings);highlightPreset()}catch(e){}}
async function loadPresets(){try{let r=await apiFetch('/api/presets');presets=await r.json();document.querySelectorAll('.preset-bar').forEach(function(bar){bar.innerHTML=presets.map(function(p,i){return '<button class="btn-sm" data-pi="'+i+'" onclick="selectPreset('+i+')">'+p.name+'</button>'}).join('')})}catch(e){}}
async function loadCameraInfo(){try{let r=await apiFetch('/api/camera/info');let info=await r.json();let sel=document.getElementById('s-framesize');sel.innerHTML='';(info.framesizes||[]).forEach(function(f){let opt=document.createElement('option');opt.value=f.value;opt.textContent=f.name+' ('+f.width+'x'+f.height+')';sel.appendChild(opt)});if(info.sensor){let sub=document.querySelector('.header .subtitle');if(sub)sub.dataset.sensor=info.sensor}}catch(e){}}

function bindSettingsListeners(){
  RANGE_FIELDS.forEach(function(k){let el=document.getElementById('s-'+k);if(el)el.addEventListener('input',function(){let vEl=document.getElementById('v-'+k);if(vEl)vEl.textContent=el.value;markUnsaved()})});
  SELECT_FIELDS.forEach(function(k){let el=document.getElementById('s-'+k);if(el)el.addEventListener('change',markUnsaved)});
  TOGGLE_FIELDS.forEach(function(k){let el=document.getElementById('s-'+k);if(el)el.addEventListener('change',markUnsaved)});
}

async function pollLogs(){if(logPaused)return;try{let r=await apiFetch('/api/logs?offset='+logOffset);let d=await r.json();if(d.size<logOffset){logOffset=0;logLines=0;document.getElementById('log-term').textContent=''}if(d.lines&&d.lines.length>0){let term=document.getElementById('log-term');term.textContent+=d.lines;let newLines=(d.lines.match(/\n/g)||[]).length;logLines+=newLines;if(logLines>250){let all=term.textContent.split('\n');term.textContent=all.slice(-200).join('\n');logLines=200}term.scrollTop=term.scrollHeight}logOffset=d.offset}catch(e){}}
async function clearLog(){try{await apiFetch('/api/logs',{method:'DELETE'})}catch(e){}logOffset=0;logLines=0;document.getElementById('log-term').textContent=''}
function toggleLogPause(){logPaused=!logPaused;document.getElementById('log-pause-btn').textContent=logPaused?'Resume':'Pause'}

var _otaXhr=null;
function otaSetIdle(){
  var btn=document.getElementById('ota-btn'),prog=document.getElementById('ota-progress'),bar=document.getElementById('ota-bar');
  btn.disabled=false;btn.className='btn-accent';btn.textContent='Upload & Flash';
  prog.style.display='none';bar.style.width='0%';bar.style.background='var(--accent)';_otaXhr=null;
}
function otaSetBusy(){
  var btn=document.getElementById('ota-btn');
  btn.className='btn-danger';btn.textContent='Cancel';btn.disabled=false;
}
function otaClick(){if(_otaXhr)otaCancel();else otaUpload()}
function otaCancel(){
  if(_otaXhr){_otaXhr.abort();_otaXhr=null}
  otaSetIdle();
  document.getElementById('ota-status').textContent='Upload cancelled';
  status('Firmware upload cancelled','info');
}
async function otaUpload(){
  let fileInput=document.getElementById('ota-file');
  if(!fileInput.files.length){status('Select a .bin file first','err');return}
  if(!confirm('This will flash new firmware and reboot the camera. Continue?'))return;
  let file=fileInput.files[0],prog=document.getElementById('ota-progress'),bar=document.getElementById('ota-bar'),st=document.getElementById('ota-status');
  prog.style.display='block';bar.style.width='0%';bar.style.background='var(--accent)';st.textContent='Uploading... 0%';status('Flashing firmware...','info');
  try{
    var xhr=new XMLHttpRequest();_otaXhr=xhr;xhr.open('POST','/api/ota',true);xhr.setRequestHeader('Content-Type','application/octet-stream');
    otaSetBusy();
    xhr.upload.onprogress=function(e){if(e.lengthComputable){let pct=Math.round(e.loaded/e.total*100);bar.style.width=pct+'%';st.textContent='Uploading... '+pct+'%'}};
    xhr.onload=function(){_otaXhr=null;otaSetIdle();try{let d=JSON.parse(xhr.responseText);if(d.ok){bar.style.width='100%';bar.style.background='var(--success)';prog.style.display='block';st.textContent='Done! Rebooting...';status('Firmware updated. Camera is rebooting...','ok')}else{bar.style.background='var(--danger)';prog.style.display='block';st.textContent='Failed: '+(d.error||'unknown error');status('OTA failed: '+(d.error||'unknown'),'err')}}catch(e){st.textContent='Unexpected response';status('OTA error','err')}};
    xhr.onerror=function(){if(!_otaXhr)return;_otaXhr=null;otaSetIdle();bar.style.background='var(--danger)';prog.style.display='block';st.textContent='Connection lost (may be rebooting)';status('Connection lost — camera may be rebooting','info')};
    xhr.send(file);
  }catch(e){otaSetIdle();st.textContent='Error: '+e.message;status('OTA error: '+e.message,'err')}
}

async function loadStatus(){try{let r=await apiFetch('/api/status');let d=await r.json();let el;el=document.getElementById('sys-sd');if(el)el.textContent=d.sd?'OK':'No SD';if(el)el.className='info-value '+(d.sd?'ok':'warn');el=document.getElementById('sys-free');if(el)el.textContent=d.free_mb+' MB';el=document.getElementById('sys-images');if(el)el.textContent=d.images}catch(e){}}

bindSettingsListeners();
loadCameraInfo().then(function(){return loadPresets()}).then(function(){return loadSettings()});
loadStatus();
refresh();
</script>
</body>
</html>
)rawliteral";

#endif // WEB_UI_H
