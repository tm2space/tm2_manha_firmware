import time
import json
import gc
import uasyncio as asyncio
import network
import binascii
import hashlib
import struct
from machine import Pin, PWM


# ---------- config ----------
DEFAULTS = {
    "gpios": [0, 1, 7, 6],
    "ssid": "manha-spinner",
    "password": "space1234",
    "pwm_freq": 400,
    "min_us": 1000,
    "center_us": 1490,
    "max_us": 2000,
    "bidirectional": True,
    "deadman_ms": 1500,
    "arm_delay_ms": 1500,
    "http_port": 80,
}
_CFG_PATH = "config.json"


def load_cfg():
    c = dict(DEFAULTS)
    try:
        with open(_CFG_PATH) as f:
            c.update(json.load(f))
    except (OSError, ValueError):
        pass
    return c


def save_cfg(c):
    keep = {k: c[k] for k in DEFAULTS if k in c}
    with open(_CFG_PATH, "w") as f:
        json.dump(keep, f)


# ---------- PPM ESC output ----------
# BLHeli SiLabs Rev14.x speaks PPM (1-2 ms pulse, 50 Hz - several hundred Hz).
# Arming: ESC auto-arms on signal + zero throttle. In bidirectional mode,
# zero = center_us (1500). In normal mode, zero = min_us (1000).
class PPMOut:
    # Each channel independently armed/disabled. Disabled = duty 0 = line LOW = ESC loses signal.
    def __init__(self, pins, freq, min_us, center_us, max_us):
        self.pins = list(pins)
        self.freq = freq
        self.period_us = 1_000_000 // freq
        self.min_us = min_us
        self.center_us = center_us
        self.max_us = max_us
        self.pwms = []
        for p in self.pins:
            pwm = PWM(Pin(p))
            pwm.freq(freq)
            pwm.duty_u16(0)
            self.pwms.append(pwm)

    def _us_to_duty(self, us):
        if us <= 0:
            return 0
        d = us * 65535 // self.period_us
        if d > 65535:
            d = 65535
        return d

    def write_us(self, idx, us):
        if idx >= len(self.pwms):
            return
        if us < self.min_us:
            us = self.min_us
        elif us > self.max_us:
            us = self.max_us
        self.pwms[idx].duty_u16(self._us_to_duty(us))

    def disable(self, idx):
        if idx >= len(self.pwms):
            return
        self.pwms[idx].duty_u16(0)

    def disable_all(self):
        for i in range(len(self.pwms)):
            self.disable(i)


# ---------- WebSocket server ----------
WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_accept(key):
    h = hashlib.sha1(key.encode() + WS_MAGIC).digest()
    return binascii.b2a_base64(h).strip()


async def _read_exact(rd, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = await rd.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


class Server:
    def __init__(self, cfg, on_ws_msg, html):
        self.cfg = cfg
        self.on_ws_msg = on_ws_msg
        self.html = html
        self.clients = set()

    async def start(self):
        ap = network.WLAN(network.AP_IF)
        ap.config(essid=self.cfg["ssid"], password=self.cfg["password"])
        ap.active(True)
        for _ in range(50):
            if ap.active():
                break
            await asyncio.sleep_ms(100)
        print("AP:", ap.ifconfig())
        await asyncio.start_server(self._handle, "0.0.0.0", self.cfg["http_port"])

    async def _handle(self, rd, wr):
        try:
            line = await rd.readline()
            if not line:
                return
            parts = line.decode().strip().split()
            if len(parts) < 2:
                return
            path = parts[1]
            headers = {}
            while True:
                ln = await rd.readline()
                if ln == b"\r\n" or not ln:
                    break
                k, _, v = ln.decode().partition(":")
                headers[k.strip().lower()] = v.strip()
            if headers.get("upgrade", "").lower() == "websocket":
                await self._ws(rd, wr, headers)
            else:
                await self._http(wr, path)
        except Exception as e:
            print("srv err:", e)
        finally:
            try:
                await wr.aclose()
            except Exception:
                try:
                    wr.close()
                except Exception:
                    pass

    async def _http(self, wr, path):
        if path in ("/", "/index.html"):
            body = self.html.encode()
            hdr = ("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                   "Content-Length: {}\r\nConnection: close\r\n\r\n").format(len(body))
            wr.write(hdr.encode())
            wr.write(body)
        elif path == "/config":
            body = json.dumps(self.cfg).encode()
            hdr = ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                   "Content-Length: {}\r\nConnection: close\r\n\r\n").format(len(body))
            wr.write(hdr.encode())
            wr.write(body)
        else:
            wr.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await wr.drain()

    async def _ws(self, rd, wr, headers):
        key = headers.get("sec-websocket-key", "")
        accept = _ws_accept(key).decode()
        resp = ("HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Accept: {}\r\n\r\n").format(accept)
        wr.write(resp.encode())
        await wr.drain()
        self.clients.add(wr)
        try:
            while True:
                msg = await self._ws_recv(rd)
                if msg is None:
                    break
                if isinstance(msg, str):
                    await self.on_ws_msg(msg, wr)
        except Exception as e:
            print("ws err:", e)
        finally:
            self.clients.discard(wr)

    async def _ws_recv(self, rd):
        hdr = await _read_exact(rd, 2)
        if not hdr:
            return None
        b1, b2 = hdr[0], hdr[1]
        op = b1 & 0x0F
        masked = b2 & 0x80
        ln = b2 & 0x7F
        if ln == 126:
            ext = await _read_exact(rd, 2)
            if not ext:
                return None
            ln = struct.unpack(">H", ext)[0]
        elif ln == 127:
            ext = await _read_exact(rd, 8)
            if not ext:
                return None
            ln = struct.unpack(">Q", ext)[0]
        if masked:
            mask = await _read_exact(rd, 4)
            if not mask:
                return None
        else:
            mask = b"\0\0\0\0"
        payload = await _read_exact(rd, ln) if ln else b""
        if payload is None:
            return None
        data = bytearray(payload)
        if masked:
            for i in range(ln):
                data[i] ^= mask[i & 3]
        if op == 0x8:
            return None
        if op == 0x1:
            return data.decode()
        return bytes(data)

    async def broadcast(self, s):
        data = s.encode() if isinstance(s, str) else s
        ln = len(data)
        hdr = bytearray([0x81])
        if ln < 126:
            hdr.append(ln)
        elif ln < 65536:
            hdr.append(126)
            hdr += struct.pack(">H", ln)
        else:
            hdr.append(127)
            hdr += struct.pack(">Q", ln)
        dead = []
        for c in list(self.clients):
            try:
                c.write(hdr)
                c.write(data)
                await c.drain()
            except Exception:
                dead.append(c)
        for c in dead:
            self.clients.discard(c)


# ---------- SPA ----------
INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RW Testbench</title>
<style>
*{box-sizing:border-box;font-family:system-ui,sans-serif}
body{margin:0;background:#0d1117;color:#c9d1d9;padding:10px;font-size:14px}
h1{font-size:17px;margin:2px 0 12px;display:flex;align-items:center;gap:8px}
.dot{width:11px;height:11px;border-radius:50%;background:#666}
.dot.ok{background:#3fb950}.dot.bad{background:#f85149}
.row{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
.btn{border:none;padding:12px 18px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;color:#fff;background:#30363d}
.btn.stop{background:#da3633;font-size:22px;padding:20px 28px}
.btn.arm{background:#1f6feb}.btn.arm.armed{background:#3fb950}.btn.arm.arming{background:#d29922}
.btn:active{transform:translateY(1px)}
.motors{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
.m{background:#161b22;padding:12px;border-radius:8px;border:1px solid #30363d}
.m h3{margin:0 0 8px;font-size:13px;display:flex;justify-content:space-between;font-weight:600}
.m input[type=range]{width:100%;accent-color:#1f6feb}
.val{font-family:ui-monospace,monospace;font-size:13px}
.status{font-family:ui-monospace,monospace;font-size:12px;color:#8b949e;margin-left:auto}
details summary{cursor:pointer;padding:8px;background:#161b22;border-radius:6px;font-weight:600}
.cfg label{display:block;margin:8px 0;font-size:12px;color:#8b949e}
.cfg input{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:7px;border-radius:4px;width:100%;font-family:ui-monospace,monospace}
</style></head><body>
<h1><span class="dot" id="dot"></span> RW Testbench <span class="status" id="status"></span></h1>
<div class="row">
  <button class="btn stop" id="stop">STOP</button>
  <button class="btn arm" id="armall">ARM ALL</button>
  <button class="btn" id="disarmall">DISARM ALL</button>
  <button class="btn" id="zero">Zero</button>
</div>
<div class="row">
  <label style="flex:1;min-width:200px">Master <span id="mv" class="val">0</span>
    <input type="range" id="master" min="-999" max="999" value="0" step="1">
  </label>
</div>
<div class="motors" id="motors"></div>
<details class="cfg" style="margin-top:14px">
<summary>Config</summary>
<label>SSID <input id="ssid"></label>
<label>Password <input id="password"></label>
<label>PWM frequency Hz <input id="pwm_freq" type="number"></label>
<label>Min pulse us <input id="min_us" type="number"></label>
<label>Center pulse us (zero throttle in bidir) <input id="center_us" type="number"></label>
<label>Max pulse us <input id="max_us" type="number"></label>
<label>Bidirectional <input id="bidirectional" type="checkbox"></label>
<label>Deadman ms <input id="deadman_ms" type="number"></label>
<label>Arm delay ms <input id="arm_delay_ms" type="number"></label>
<label>GPIOs M1,M2,M3,M4 <input id="gpios"></label>
<button class="btn" id="save">Save</button>
<div style="font-size:11px;color:#8b949e;margin-top:6px">SSID/password/GPIO/PWM freq need reboot. min/center/max us apply live. 3D mode must be set via BLHeliSuite. If arming stalls at first beep: find the slider dead-spot (motor does not respond), take the midpoint UI value v, set center_us = 1500 + 500*v/999.</div>
</details>
<script>
const motorsEl=document.getElementById('motors'),dot=document.getElementById('dot'),status=document.getElementById('status');
let ws;
const throttles=[0,0,0,0];
const modes=['idle','idle','idle','idle'];
for(let i=0;i<4;i++){
  const d=document.createElement('div');d.className='m';
  d.innerHTML=`<h3>M${i+1} <span class="val" id="v${i}">0</span> <span class="val rpm" id="u${i}">— us</span></h3>
    <input type="range" min="-999" max="999" value="0" step="1" id="s${i}">
    <div style="display:flex;gap:6px;margin-top:8px"><button class="btn arm" id="a${i}" style="flex:1;padding:8px 12px;font-size:13px">ARM</button></div>`;
  motorsEl.appendChild(d);
  const s=document.getElementById('s'+i);
  s.oninput=()=>{throttles[i]=+s.value;document.getElementById('v'+i).textContent=throttles[i];push();};
  s.onchange=()=>{throttles[i]=+s.value;pushFinal();};
  document.getElementById('a'+i).onclick=()=>send({op:modes[i]==='armed'?'disarm':'arm', i:i});
}
document.getElementById('master').oninput=e=>{
  const v=+e.target.value;document.getElementById('mv').textContent=v;
  for(let i=0;i<4;i++){throttles[i]=v;document.getElementById('s'+i).value=v;document.getElementById('v'+i).textContent=v;}
  push();
};
document.getElementById('master').onchange=()=>pushFinal();
document.getElementById('zero').onclick=()=>{
  for(let i=0;i<4;i++){throttles[i]=0;document.getElementById('s'+i).value=0;document.getElementById('v'+i).textContent=0;}
  document.getElementById('master').value=0;document.getElementById('mv').textContent=0;push();
};
document.getElementById('stop').onclick=()=>send({op:'stop'});
document.getElementById('armall').onclick=()=>send({op:'arm'});
document.getElementById('disarmall').onclick=()=>send({op:'disarm'});
document.getElementById('save').onclick=()=>send({
  op:'set_config',ssid:ssid.value,password:password.value,
  pwm_freq:+pwm_freq.value,min_us:+min_us.value,center_us:+center_us.value,max_us:+max_us.value,
  bidirectional:bidirectional.checked,
  deadman_ms:+deadman_ms.value,arm_delay_ms:+arm_delay_ms.value,
  gpios:gpios.value.split(',').map(s=>+s.trim()).filter(n=>!isNaN(n)),
});
let lastPush=0,pendingPush=null;
const PUSH_MIN_MS=80;
function push(){
  const now=Date.now();
  const dt=now-lastPush;
  if(dt>=PUSH_MIN_MS){lastPush=now;send({op:'throttle',v:throttles.slice()});if(pendingPush){clearTimeout(pendingPush);pendingPush=null;}}
  else if(!pendingPush){pendingPush=setTimeout(()=>{lastPush=Date.now();send({op:'throttle',v:throttles.slice()});pendingPush=null;},PUSH_MIN_MS-dt);}
}
function pushFinal(){if(pendingPush){clearTimeout(pendingPush);pendingPush=null;}lastPush=Date.now();send({op:'throttle',v:throttles.slice()});}
function send(o){if(ws&&ws.readyState===1)ws.send(JSON.stringify(o));}
function connect(){
  ws=new WebSocket('ws://'+location.host+'/ws');
  ws.onopen=()=>{dot.className='dot ok';setInterval(()=>send({op:'ping',t:Date.now()}),400);};
  ws.onclose=()=>{dot.className='dot bad';setTimeout(connect,1000);};
  ws.onmessage=m=>{
    const d=JSON.parse(m.data);
    if(d.op==='pong'){status.textContent='ping '+(Date.now()-d.t)+'ms';}
    else if(d.op==='tlm'){
      const ms_=d.modes||[],us_=d.us||[];
      let anyArmed=false,anyArming=false;
      for(let i=0;i<4;i++){
        modes[i]=ms_[i]||'idle';
        const b=document.getElementById('a'+i);
        b.classList.toggle('armed',modes[i]==='armed');
        b.classList.toggle('arming',modes[i]==='arming');
        b.textContent=modes[i]==='arming'?'ARMING...':(modes[i]==='armed'?'ARMED':'ARM');
        if(modes[i]==='armed')anyArmed=true;
        if(modes[i]==='arming')anyArming=true;
        const u=us_[i]||0;
        document.getElementById('u'+i).textContent=(u?u:'off')+(u?' us':'');
      }
      const ball=document.getElementById('armall');
      ball.classList.toggle('armed',anyArmed&&!anyArming);
      ball.classList.toggle('arming',anyArming);
    }else if(d.op==='config_saved'){status.textContent='saved';}
  };
}
fetch('/config').then(r=>r.json()).then(c=>{
  ssid.value=c.ssid;password.value=c.password;
  pwm_freq.value=c.pwm_freq;min_us.value=c.min_us;center_us.value=c.center_us;max_us.value=c.max_us;
  bidirectional.checked=!!c.bidirectional;
  deadman_ms.value=c.deadman_ms;arm_delay_ms.value=c.arm_delay_ms;
  gpios.value=(c.gpios||[]).join(',');
});
connect();
</script></body></html>"""


# ---------- state + logic ----------
cfg = load_cfg()

# Per-wheel mode: "idle" | "arming" | "armed"
state = {
    "wheels": [{"mode": "idle", "arm_t0": 0} for _ in range(4)],
    "throttles": [0, 0, 0, 0],
    "us_out": [0, 0, 0, 0],
    "last_cmd_ms": 0,
}

ppm = None
server = None


def ms():
    return time.ticks_ms()


def map_us(v):
    # UI throttle [-999, 999] → pulse microseconds.
    # Bidir: -999→min_us, 0→center_us, +999→max_us
    # Fwd-only (bidirectional=False): any v>=0 linear 0..999 → center_us..max_us
    if v > 999:
        v = 999
    elif v < -999:
        v = -999
    c = cfg["center_us"]
    if cfg.get("bidirectional", True):
        if v >= 0:
            return c + (cfg["max_us"] - c) * v // 999
        return c + (c - cfg["min_us"]) * v // 999
    if v < 0:
        v = 0
    return cfg["min_us"] + (cfg["max_us"] - cfg["min_us"]) * v // 999


def _arm_one(i):
    w = state["wheels"][i]
    if w["mode"] == "idle":
        w["mode"] = "arming"
        w["arm_t0"] = ms()


def _disarm_one(i):
    state["wheels"][i]["mode"] = "idle"
    state["throttles"][i] = 0


async def handle_ws(msg, _client):
    try:
        d = json.loads(msg)
    except ValueError:
        return
    op = d.get("op")
    state["last_cmd_ms"] = ms()
    if op == "ping":
        await server.broadcast(json.dumps({"op": "pong", "t": d.get("t", 0)}))
    elif op == "arm":
        i = d.get("i")
        if i is None:
            for k in range(len(state["wheels"])):
                _arm_one(k)
        else:
            _arm_one(int(i))
    elif op == "disarm":
        i = d.get("i")
        if i is None:
            for k in range(len(state["wheels"])):
                _disarm_one(k)
        else:
            _disarm_one(int(i))
    elif op == "stop":
        for k in range(len(state["wheels"])):
            _disarm_one(k)
    elif op == "throttle":
        vs = d.get("v", [0, 0, 0, 0])
        for i, v in enumerate(vs[:4]):
            if state["wheels"][i]["mode"] == "armed":
                state["throttles"][i] = int(v)
    elif op == "set_config":
        for k in ("ssid", "password", "pwm_freq", "min_us", "center_us", "max_us",
                  "bidirectional", "deadman_ms", "arm_delay_ms", "gpios"):
            if k in d:
                cfg[k] = d[k]
        save_cfg(cfg)
        ppm.min_us = cfg["min_us"]
        ppm.center_us = cfg["center_us"]
        ppm.max_us = cfg["max_us"]
        await server.broadcast(json.dumps({"op": "config_saved"}))


async def tx_loop():
    while True:
        now = ms()
        deadman = time.ticks_diff(now, state["last_cmd_ms"]) > cfg["deadman_ms"]
        # Arming ramp: zero (phase1) → up-throttle (phase2) → zero (phase3) → armed.
        total = cfg["arm_delay_ms"]
        p1 = total * 2 // 10       # 20%: initial zero hold
        p2 = total * 6 // 10       # 60% cumulative: up-throttle
        up_val = 200               # ~20% of bidir forward
        state["us_out"] = [0, 0, 0, 0]
        for i, w in enumerate(state["wheels"]):
            m = w["mode"]
            if m == "idle":
                ppm.disable(i)
            elif m == "arming":
                el = time.ticks_diff(now, w["arm_t0"])
                if el < p1:
                    tgt = map_us(0)
                elif el < p2:
                    tgt = map_us(up_val)
                elif el < total:
                    tgt = map_us(0)
                else:
                    w["mode"] = "armed"
                    tgt = map_us(0)
                ppm.write_us(i, tgt)
                state["us_out"][i] = tgt
            else:  # armed
                if deadman:
                    w["mode"] = "idle"
                    state["throttles"][i] = 0
                    ppm.disable(i)
                else:
                    tgt = map_us(state["throttles"][i])
                    ppm.write_us(i, tgt)
                    state["us_out"][i] = tgt
        await asyncio.sleep_ms(20)


async def tlm_loop():
    while True:
        try:
            await server.broadcast(json.dumps({
                "op": "tlm",
                "modes": [w["mode"] for w in state["wheels"]],
                "throttles": state["throttles"],
                "us": state["us_out"],
            }))
        except Exception as e:
            print("bcast err:", e)
        await asyncio.sleep_ms(500)


async def main():
    global ppm, server
    ppm = PPMOut(cfg["gpios"], cfg["pwm_freq"],
                 cfg["min_us"], cfg["center_us"], cfg["max_us"])
    state["last_cmd_ms"] = ms()
    server = Server(cfg, handle_ws, INDEX_HTML)
    await server.start()
    asyncio.create_task(tx_loop())
    asyncio.create_task(tlm_loop())
    print("ready: http://192.168.4.1/")
    while True:
        await asyncio.sleep(1)
        gc.collect()


asyncio.run(main())
