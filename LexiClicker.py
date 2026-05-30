#!/usr/bin/env python3
"""
LexiClicker Pro v2 — Real-time Web Controller Edition
pip install pyautogui keyboard flask flask-cors pynput flaskwebgui pystray pillow
"""

import threading, sys, os, json, ctypes
import pyautogui
import keyboard
import time
import random
import datetime
from flask import send_from_directory, Flask, request, jsonify, Response
from flask_cors import CORS
from flaskwebgui import FlaskUI
from pynput.mouse import Button, Controller as MouseController

APP_NAME    = "LexiClicker"
APP_VERSION = "Pro v2"

if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    data_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = base_dir

SAVE_FILE = os.path.join(data_dir, 'lexiclicker_save.json')
ICON_ICO  = os.path.join(base_dir, 'AutoClicker.ico')
ICON_PNG  = os.path.join(base_dir, 'AutoClicker.png')
SOUNDS_DIR = os.path.join(data_dir, 'sounds')
BUILTIN_SOUNDS = [
    'click1.wav','click2.wav','clickangry.wav','roboclick.wav',
    'peanutdrop.wav','pop1.wav','pop2.wav','tap1.wav','waterdrop.wav','vineboom.wav',
]
PIANO_SOUNDS = ['pianoa3.wav','pianob3.wav','pianof4.wav','pianog4.wav','pianog4_2.wav']

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LexiClicker.Pro.v2")
except Exception:
    pass

app = Flask(__name__,
    template_folder=os.path.join(base_dir, 'templates'),
    static_folder=os.path.join(base_dir, 'static'))
CORS(app)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0

_mouse = MouseController()

DEFAULT_CFG = {
    "interval_mode":    "fixed",
    "interval":         100,
    "rand_min":         50,
    "rand_max":         500,
    "human_cps":        4,
    "mouse_btn":        "left",
    "double_click":     False,
    "invisible_click":  False,
    "loc_mode":         "fixed",
    "fixed_x":          500,
    "fixed_y":          300,
    "rand_radius_x":    100,
    "rand_radius_y":    100,
    "repeat_mode":      "infinite",
    "repeat_count":     100,
    "duration_ms":      60000,
    "jitter":           2,
    "move_duration":    0.05,
    "hotkey":           "f6",
    "stop_key":         "escape",
    "set_pos_hotkey":   "f8",
    "set_pos_hotkey_on": True,
    "stop_cooldown_on":  True,
    "stop_cooldown_sec": 3,
    "restart_hotkey":    "",
    "restart_hotkey_on": False,
    "restart_bypass_cooldown": False,
}

lock  = threading.Lock()
state = {
    "running":        False,
    "click_count":    0,
    "session_clicks": 0,
    "cps":            0.0,
    "sequence":       [],
    "cfg":            dict(DEFAULT_CFG),
    "win_w":          1100,
    "win_h":          780,
    "last_click":     None,
}
stop_event  = threading.Event()
cps_window  = []
start_time  = None
click_events = []
MAX_CLICK_EVENTS = 50
_tray_icon  = None
_flaskui    = None
_mintray_enabled = True
_human_moved = False
_bot_moving = False

# ── Persistence ────────────────────────────────────────────────────────────────

def load_save():
    if not os.path.exists(SAVE_FILE): return
    try:
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for k, v in data.get('cfg', {}).items():
            if k in state['cfg']:
                old = state['cfg'][k]
                if isinstance(old, bool):  state['cfg'][k] = bool(v)
                elif isinstance(old, int): state['cfg'][k] = int(v)
                elif isinstance(old, float): state['cfg'][k] = float(v)
                else: state['cfg'][k] = v
        state['sequence']    = data.get('sequence', [])
        state['click_count'] = int(data.get('click_count', 0))
        state['win_w']       = data.get('win_w', 1100)
        state['win_h']       = data.get('win_h', 780)
        print(f"[LexiClicker] Loaded {SAVE_FILE}")
    except Exception as e:
        print(f"[LexiClicker] Load warning: {e}")

def persist_save():
    try:
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'cfg':         state['cfg'],
                'sequence':    state['sequence'],
                'click_count': state['click_count'],
                'win_w':       state.get('win_w', 1100),
                'win_h':       state.get('win_h', 780),
            }, f, indent=2)
    except Exception as e:
        print(f"[LexiClicker] Save warning: {e}")

# ── Click logic ────────────────────────────────────────────────────────────────

def get_delay():
    c, m = state["cfg"], state["cfg"]["interval_mode"]
    if m == "fixed":  return c["interval"] / 1000
    if m == "random": return random.uniform(c["rand_min"]/1000, c["rand_max"]/1000)
    if m == "human":
        base = 1.0 / max(c["human_cps"], 0.1)
        return max(0.001, base + random.gauss(0, base * 0.15))
    return 0.1

def get_position(step=None):
    c  = state["cfg"]
    jx = random.randint(-c["jitter"], c["jitter"]) if c["jitter"] > 0 else 0
    jy = random.randint(-c["jitter"], c["jitter"]) if c["jitter"] > 0 else 0
    if step: return step["x"]+jx, step["y"]+jy
    if c["loc_mode"] == "fixed":
        return c["fixed_x"]+jx, c["fixed_y"]+jy
    if c["loc_mode"] == "random":
        return (c["fixed_x"]+random.randint(-c["rand_radius_x"],c["rand_radius_x"])+jx,
                c["fixed_y"]+random.randint(-c["rand_radius_y"],c["rand_radius_y"])+jy)
    cx, cy = pyautogui.position()
    return cx+jx, cy+jy

def do_click(x, y, button="left", double=False):
    btn = {"left": Button.left, "right": Button.right, "middle": Button.middle}.get(button, Button.left)
    with lock:
        t_now = time.time()
        state["last_click"] = {"x": x, "y": y, "t": t_now}
        click_events.append({"x": x, "y": y, "t": t_now})
        if len(click_events) > MAX_CLICK_EVENTS:
            click_events.pop(0)
    if state["cfg"].get("invisible_click", False):
        orig = _mouse.position
        _mouse.position = (x, y)
        if double: _mouse.click(btn, 1); time.sleep(0.05); _mouse.click(btn, 1)
        else:      _mouse.click(btn, 1)
        _mouse.position = orig
    else:
        global _bot_moving
        _bot_moving = True
        pyautogui.moveTo(x, y, duration=state['cfg']['move_duration'])
        _bot_moving = False
        if double: pyautogui.doubleClick(button=button)
        else:      pyautogui.click(button=button)

def update_cps():
    global cps_window
    now = time.time()
    cps_window = [t for t in cps_window if now - t < 1.0]
    with lock: state["cps"] = round(len(cps_window), 1)

def clicker_loop():
    global cps_window, start_time
    with lock:
        state["session_clicks"] = 0
        start_time = time.time()
    cps_window = []
    c         = state["cfg"]
    seq_mode  = c["loc_mode"] == "sequence"
    seq_index = iteration = 0
    print(f"[LexiClicker] Started — {c['interval_mode']}/{c['loc_mode']}/{c['repeat_mode']}")

    while not stop_event.is_set():
        if seq_mode and state["sequence"]:
            enabled = [s for s in state["sequence"] if s.get("enabled", True)]
            if not enabled: time.sleep(0.1); continue
            step = enabled[seq_index % len(enabled)]; seq_index += 1
            x, y = get_position(step)
            do_click(x, y, step.get("button", c["mouse_btn"]), c["double_click"])
            cps_window.append(time.time()); update_cps()
            with lock:
                state["session_clicks"] += 1
                state["click_count"]    += 1
            stop_event.wait(step.get("delay", get_delay()))
            if seq_index % len(enabled) == 0:
                iteration += 1
                if c["repeat_mode"] == "count" and iteration >= c["repeat_count"]: break
        else:
            x, y = get_position()
            do_click(x, y, c["mouse_btn"], c["double_click"])
            cps_window.append(time.time()); update_cps()
            with lock:
                state["session_clicks"] += 1
                state["click_count"]    += 1
            if c["repeat_mode"] == "count" and state["session_clicks"] >= c["repeat_count"]: break

        if c["repeat_mode"] == "duration" and (time.time()-start_time)*1000 >= c["duration_ms"]: break
        if not seq_mode: stop_event.wait(get_delay())

    with lock: state["running"] = False
    persist_save()
    print(f"[LexiClicker] Stopped — {state['session_clicks']} clicks")

def start_clicker():
    with lock:
        if state["running"]: return
        state["running"] = True
    stop_event.clear()
    threading.Thread(target=clicker_loop, daemon=True).start()

def stop_clicker():
    """Hard stop — sets stop_event immediately to cancel any in-progress wait."""
    stop_event.set()
    with lock: state["running"] = False

def toggle_clicker():
    stop_clicker() if state["running"] else start_clicker()

def restart_clicker():
    """Start clicker directly — cooldown bypass handled in frontend."""
    if not state["running"]:
        start_clicker()

# ── Tray / window helpers ───────────────────────────────────────────────────────

def show_window():
    try:
        user32 = ctypes.windll.user32
        WINFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        found = []
        def cb(hwnd, n):
            if user32.GetWindowTextLengthW(hwnd) > 0:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if APP_NAME in buf.value: found.append(hwnd)
            return True
        user32.EnumWindows(WINFUNC(cb), 0)
        for hwnd in found:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"[LexiClicker] show_window error: {e}")

def on_close_intercept():
    if _mintray_enabled:
        try:
            user32 = ctypes.windll.user32
            WINFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            found = []
            def cb(hwnd, n):
                if user32.GetWindowTextLengthW(hwnd) > 0:
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, buf, 256)
                    if APP_NAME in buf.value: found.append(hwnd)
                return True
            user32.EnumWindows(WINFUNC(cb), 0)
            for hwnd in found: user32.ShowWindow(hwnd, 0)
        except Exception as e:
            print(f"[LexiClicker] hide error: {e}")
    else:
        persist_save(); stop_clicker(); os._exit(0)

def on_mouse_move(x, y):
    global _human_moved
    if _bot_moving:
        return
    # Ignore moves within 15px of last click target (bot precision landing)
    lc = state.get("last_click")
    if lc:
        if (x - lc["x"])**2 + (y - lc["y"])**2 < 225:
            return
    _human_moved = True
    # Direct stop — no HTTP round-trip delay
    if state["running"] and state["cfg"].get("stop_on_blur", False):
        stop_clicker()

# ── Flask routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(base_dir, 'auto-clicker-controller.html')

@app.route("/AutoClicker.png")
def favicon_png():
    return send_from_directory(base_dir, 'AutoClicker.png')

@app.route("/AutoClicker.ico")
@app.route("/favicon.ico")
def favicon_ico():
    for name in ['AutoClicker.ico', 'AutoClicker.png']:
        path = os.path.join(base_dir, name)
        if os.path.exists(path):
            return send_from_directory(base_dir, name)
    return '', 204

@app.route("/status")
def api_status():
    elapsed = int((time.time()-start_time)*1000) if start_time and state["running"] else 0
    with lock:
        return jsonify({
            "running":        state["running"],
            "session_clicks": state["session_clicks"],
            "click_count":    state["click_count"],
            "cps":            state["cps"],
            "elapsed_ms":     elapsed,
            "cfg":            state["cfg"],
            "sequence_len":   len(state["sequence"]),
            "last_click":     state.get("last_click"),
        })

@app.route("/clicks_since")
def api_clicks_since():
    try:
        since = float(request.args.get("t", 0))
    except (ValueError, TypeError):
        since = 0.0
    with lock:
        events = [e for e in click_events if e["t"] > since]
    return jsonify({"events": events})

@app.route("/start", methods=["POST"])
def api_start():
    if not state["running"]: start_clicker()
    return jsonify({"ok": True, "running": state["running"]})

@app.route("/stop", methods=["POST"])
def api_stop():
    """Hard stop — sets stop_event immediately."""
    stop_event.set()
    with lock: state["running"] = False
    return jsonify({"ok": True, "running": False})

@app.route("/toggle", methods=["POST"])
def api_toggle(): toggle_clicker(); return jsonify({"ok": True, "running": state["running"]})

@app.route("/restart", methods=["POST"])
def api_restart():
    """Restart clicker — frontend decides whether to respect cooldown."""
    restart_clicker()
    return jsonify({"ok": True, "running": state["running"]})

@app.route("/close_or_hide", methods=["POST", "GET"])
def api_close_or_hide():
    on_close_intercept()
    return jsonify({"ok": True})

@app.route("/show_window", methods=["POST"])
def api_show_window():
    show_window()
    return jsonify({"ok": True})

@app.route("/set_mintray", methods=["POST"])
def api_set_mintray():
    global _mintray_enabled
    data = request.get_json(force=True)
    _mintray_enabled = bool(data.get("enabled", True))
    return jsonify({"ok": True})

@app.route("/window_pos")
def api_window_pos():
    try:
        user32 = ctypes.windll.user32
        WINFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        found = []
        def cb(hwnd, n):
            if user32.GetWindowTextLengthW(hwnd) > 0:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if APP_NAME in buf.value: found.append(hwnd)
            return True
        user32.EnumWindows(WINFUNC(cb), 0)
        if found:
            from ctypes import wintypes
            pt = wintypes.POINT(0, 0)
            user32.ClientToScreen(found[0], ctypes.byref(pt))
            return jsonify({"x": pt.x, "y": pt.y})
    except Exception as e:
        print(f"[LexiClicker] window_pos error: {e}")
    return jsonify({"x": 0, "y": 0})

@app.route("/rebind_hotkeys", methods=["POST"])
def api_rebind_hotkeys():
    bind_hotkeys()
    return jsonify({"ok": True})

@app.route("/config", methods=["POST"])
def api_config():
    data = request.get_json(force=True)
    with lock:
        for k, v in data.items():
            if k in state["cfg"]:
                old = state["cfg"][k]
                if isinstance(old, bool):   state["cfg"][k] = bool(v)
                elif isinstance(old, int):  state["cfg"][k] = int(v)
                elif isinstance(old, float):state["cfg"][k] = float(v)
                else: state["cfg"][k] = v
    persist_save()
    return jsonify({"ok": True, "cfg": state["cfg"]})

@app.route("/sequence", methods=["GET"])
def api_get_sequence(): return jsonify(state["sequence"])

@app.route("/sequence", methods=["POST"])
def api_set_sequence():
    with lock: state["sequence"] = request.get_json(force=True)
    persist_save(); return jsonify({"ok": True})

@app.route("/sequence/add", methods=["POST"])
def api_add_step():
    step = request.get_json(force=True)
    step.setdefault("enabled", True); step.setdefault("button", "left")
    step.setdefault("delay", 0.3);    step.setdefault("label", f"Step {len(state['sequence'])+1}")
    with lock: state["sequence"].append(step)
    persist_save(); return jsonify({"ok": True, "step": step})

@app.route("/sequence/clear", methods=["POST"])
def api_clear_sequence():
    with lock: state["sequence"] = []
    persist_save(); return jsonify({"ok": True})

@app.route("/mouse_moved")
def api_mouse_moved():
    global _human_moved
    moved = _human_moved
    _human_moved = False
    return jsonify({"moved": moved})

@app.route("/cursor")
def api_cursor():
    x, y = pyautogui.position()
    return jsonify({"x": x, "y": y})

@app.route("/cursor/save", methods=["POST"])
def api_save_cursor():
    x, y = pyautogui.position()
    with lock:
        state["cfg"]["fixed_x"] = x
        state["cfg"]["fixed_y"] = y
    persist_save(); return jsonify({"ok": True, "x": x, "y": y})

@app.route("/reset_count", methods=["POST"])
def api_reset():
    with lock: state["click_count"] = 0
    persist_save(); return jsonify({"ok": True})

@app.route("/save_state", methods=["POST"])
def api_save_state():
    data = request.get_json(force=True, silent=True) or {}
    for k in ('win_w', 'win_h'):
        if k in data: state[k] = data[k]
    persist_save(); return jsonify({"ok": True})

@app.route("/quit", methods=["POST"])
def api_quit():
    persist_save()
    stop_clicker()
    threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/export_settings", methods=["GET"])
def api_export_settings():
    pf = os.path.join(data_dir, 'lexiclicker_presets.json')
    custom_presets = json.load(open(pf, 'r', encoding='utf-8')) if os.path.exists(pf) else []
    bundle = {
        "version": 2, "cfg": state["cfg"], "sequence": state["sequence"],
        "custom_presets": custom_presets, "exported_at": datetime.datetime.now().isoformat(),
    }
    fname = f"lexiclicker_settings_{datetime.date.today()}.json"
    return Response(json.dumps(bundle, indent=2), mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'})

@app.route("/import_settings", methods=["POST"])
def api_import_settings():
    bundle = request.get_json(force=True)
    if not bundle or 'cfg' not in bundle:
        return jsonify({"ok": False, "error": "Invalid bundle"}), 400
    with lock:
        for k, v in bundle.get('cfg', {}).items():
            if k in state['cfg']:
                old = state['cfg'][k]
                if isinstance(old, bool):   state['cfg'][k] = bool(v)
                elif isinstance(old, int):  state['cfg'][k] = int(v)
                elif isinstance(old, float):state['cfg'][k] = float(v)
                else: state['cfg'][k] = v
        if 'sequence' in bundle: state['sequence'] = bundle['sequence']
        if 'custom_presets' in bundle:
            pf = os.path.join(data_dir, 'lexiclicker_presets.json')
            json.dump(bundle['custom_presets'], open(pf, 'w', encoding='utf-8'), indent=2)
    persist_save()
    return jsonify({"ok": True})

@app.route("/minimize_to_tray", methods=["POST"])
def api_minimize_tray():
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        found = []
        def enum_cb(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if APP_NAME in buf.value: found.append(hwnd)
            return True
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        for hwnd in found: user32.ShowWindow(hwnd, 0)
        if not found: print("[LexiClicker] No window found to minimize")
    except Exception as e:
        print(f"[LexiClicker] Minimize error: {e}")
    return jsonify({"ok": True})

@app.route("/presets", methods=["GET"])
def api_get_presets():
    pf = os.path.join(data_dir, 'lexiclicker_presets.json')
    return jsonify(json.load(open(pf, 'r', encoding='utf-8')) if os.path.exists(pf) else [])

@app.route("/presets", methods=["POST"])
def api_save_preset():
    pf = os.path.join(data_dir, 'lexiclicker_presets.json')
    presets = json.load(open(pf, 'r', encoding='utf-8')) if os.path.exists(pf) else []
    p = request.get_json(force=True)
    presets = [x for x in presets if x.get('name') != p.get('name')]
    presets.append(p)
    json.dump(presets, open(pf, 'w', encoding='utf-8'), indent=2)
    return jsonify({"ok": True})

@app.route("/presets/<name>", methods=["DELETE"])
def api_delete_preset(name):
    pf = os.path.join(data_dir, 'lexiclicker_presets.json')
    if os.path.exists(pf):
        presets = [p for p in json.load(open(pf, 'r', encoding='utf-8')) if p.get('name') != name]
        json.dump(presets, open(pf, 'w', encoding='utf-8'), indent=2)
    return jsonify({"ok": True})

@app.route("/sounds/list")
def api_sounds_list():
    found = []
    if os.path.exists(SOUNDS_DIR):
        for f in sorted(os.listdir(SOUNDS_DIR)):
            if f.lower().endswith(('.wav', '.mp3', '.ogg', '.flac')):
                found.append(f)
    builtin_dir = os.path.join(base_dir, 'sounds')
    if builtin_dir != SOUNDS_DIR and os.path.exists(builtin_dir):
        for f in sorted(os.listdir(builtin_dir)):
            if f.lower().endswith(('.wav', '.mp3', '.ogg', '.flac')) and f not in found:
                found.append(f)
    return jsonify({
        "builtin":  BUILTIN_SOUNDS,
        "piano":    PIANO_SOUNDS,
        "uploaded": [f for f in found if f not in BUILTIN_SOUNDS and f not in PIANO_SOUNDS],
        "all":      found,
    })

@app.route("/sounds/<path:filename>")
def serve_sound(filename):
    safe = os.path.basename(filename)
    if os.path.exists(SOUNDS_DIR) and os.path.exists(os.path.join(SOUNDS_DIR, safe)):
        return send_from_directory(SOUNDS_DIR, safe)
    builtin_path = os.path.join(base_dir, 'sounds', safe)
    if os.path.exists(builtin_path):
        return send_from_directory(os.path.join(base_dir, 'sounds'), safe)
    flat_path = os.path.join(base_dir, safe)
    if os.path.exists(flat_path):
        return send_from_directory(base_dir, safe)
    return '', 404

@app.route("/sounds/upload", methods=["POST"])
def api_upload_sound():
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    saved = []
    for f in request.files.getlist('files'):
        if f and f.filename:
            safe = os.path.basename(f.filename)
            if safe.lower().endswith(('.wav', '.mp3', '.ogg', '.flac')):
                f.save(os.path.join(SOUNDS_DIR, safe))
                saved.append(safe)
    return jsonify({"ok": True, "saved": saved})

# ── Hotkeys ────────────────────────────────────────────────────────────────────

def save_cursor_pos():
    x, y = pyautogui.position()
    with lock:
        state["cfg"]["fixed_x"] = x
        state["cfg"]["fixed_y"] = y
    persist_save()
    print(f"[LexiClicker] Pos saved: {x},{y}")

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL HOTKEY SYSTEM — pynput only, works when ANY window is focused
# Replaces keyboard.add_hotkey so toggle/stop/save_pos work in-game
# ══════════════════════════════════════════════════════════════════════════════
try:
    from pynput import mouse as _pm, keyboard as _pk
    _pynput_ok = True
except ImportError:
    _pynput_ok = False
    print("[LexiClicker] WARNING: pynput not installed. pip install pynput")

_gl_mouse_listener    = None
_gl_kb_listener       = None
_gl_pressed_keys: set = set()   # track held modifiers

def _hk_map():
    """Return list of (hotkey_str, callable) from current cfg."""
    cfg = state["cfg"]
    pairs = [
        (cfg.get("hotkey",   "f6"),      toggle_clicker),
        (cfg.get("stop_key", "escape"),  stop_clicker),
    ]
    if cfg.get("set_pos_hotkey_on", True):
        pairs.append((cfg.get("set_pos_hotkey", "f8"), save_cursor_pos))
    if cfg.get("restart_hotkey_on", False) and cfg.get("restart_hotkey", ""):
        pairs.append((cfg.get("restart_hotkey", ""), restart_clicker))
    return [(hk.lower().strip(), fn) for hk, fn in pairs if hk]

def _parse_hk(hk):
    """Split 'ctrl+alt+f5' → (frozenset({'ctrl','alt'}), 'f5')."""
    if hk.startswith("mouse") or hk in ("wheelup", "wheeldown"):
        return None, hk          # mouse / scroll — no mods
    parts = hk.split("+")
    mods  = frozenset(p for p in parts[:-1] if p in ("ctrl","alt","shift","cmd"))
    key   = parts[-1]
    return mods, key

def _active_mods():
    return frozenset(k for k in _gl_pressed_keys
                     if k in ("ctrl","alt","shift","cmd"))

# ── pynput key name normaliser ─────────────────────────────────────────────────
_PYNPUT_KEY_NAMES = {
    "ctrl_l":"ctrl","ctrl_r":"ctrl",
    "alt_l":"alt","alt_r":"alt","alt_gr":"alt",
    "shift_l":"shift","shift_r":"shift",
    "cmd_l":"cmd","cmd_r":"cmd",
    "esc":"escape",
    "f1":"f1","f2":"f2","f3":"f3","f4":"f4","f5":"f5","f6":"f6",
    "f7":"f7","f8":"f8","f9":"f9","f10":"f10","f11":"f11","f12":"f12",
}

def _pynput_key_str(key):
    try:
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        name = key.name.lower() if hasattr(key, "name") else str(key).lower()
        return _PYNPUT_KEY_NAMES.get(name, name)
    except Exception:
        return ""

def _on_key_press(key):
    ks = _pynput_key_str(key)
    if not ks: return
    _gl_pressed_keys.add(ks)
    mods = _active_mods()
    for hk, fn in _hk_map():
        req_mods, req_key = _parse_hk(hk)
        if req_mods is not None and ks == req_key and mods == req_mods:
            fn()

def _on_key_release(key):
    ks = _pynput_key_str(key)
    _gl_pressed_keys.discard(ks)

# ── Mouse button map ──────────────────────────────────────────────────────────
def _get_mouse_btn_name(button):
    try:
        from pynput.mouse import Button as Btn
        _bmap = {
            Btn.left:   "mouse1",
            Btn.right:  "mouse2",
            Btn.middle: "mouse3",
        }
        try:   _bmap[Btn.x1] = "mouse4"
        except Exception: pass
        try:   _bmap[Btn.x2] = "mouse5"
        except Exception: pass
        return _bmap.get(button)
    except Exception:
        return None

def _on_mouse_click(x, y, button, pressed):
    if not pressed: return
    bn = _get_mouse_btn_name(button)
    if not bn: return
    for hk, fn in _hk_map():
        req_mods, req_key = _parse_hk(hk)
        if req_mods is None and req_key == bn:
            fn()

def _on_scroll(x, y, dx, dy):
    sn = "wheelup" if dy > 0 else "wheeldown"
    for hk, fn in _hk_map():
        req_mods, req_key = _parse_hk(hk)
        if req_mods is None and req_key == sn:
            fn()

def start_global_listeners():
    """Start / restart OS-level pynput listeners. Call after any hotkey change."""
    global _gl_mouse_listener, _gl_kb_listener
    if not _pynput_ok:
        print("[LexiClicker] pynput unavailable — hotkeys will NOT work when unfocused")
        return
    # Stop old listeners
    for lst in (_gl_mouse_listener, _gl_kb_listener):
        try:
            if lst: lst.stop()
        except Exception: pass
    _gl_pressed_keys.clear()
    try:
        _gl_mouse_listener = _pm.Listener(on_click=_on_mouse_click, on_scroll=_on_scroll, on_move=on_mouse_move, daemon=True)
        _gl_mouse_listener.start()
        _gl_kb_listener = _pk.Listener(
            on_press=_on_key_press, on_release=_on_key_release, daemon=True)
        _gl_kb_listener.start()
        cfg = state["cfg"]
        pos_hk = cfg.get("set_pos_hotkey","f8") if cfg.get("set_pos_hotkey_on",True) else "off"
        print(f"[LexiClicker] Global hotkeys active (works in-game): "
              f"{cfg['hotkey'].upper()}=toggle  "
              f"{cfg['stop_key'].upper()}=stop  "
              f"{pos_hk.upper()}=save_pos")
    except Exception as e:
        print(f"[LexiClicker] Listener error: {e}")

def bind_hotkeys():
    """Re-register hotkeys — just restarts pynput listeners with fresh cfg."""
    start_global_listeners()




def start_tray():
    global _tray_icon
    try:
        import pystray
        from PIL import Image as PILImage

        icon_img = None
        for path in [ICON_PNG, ICON_ICO]:
            if os.path.exists(path):
                try:
                    icon_img = PILImage.open(path).convert("RGBA").resize((64, 64), PILImage.LANCZOS)
                    print(f"[LexiClicker] Tray icon: {path}")
                    break
                except Exception as ie:
                    print(f"[LexiClicker] Icon fail {path}: {ie}")

        if icon_img is None:
            from PIL import ImageDraw
            icon_img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(icon_img)
            d.ellipse([4, 4, 60, 60], fill=(61, 158, 168, 255))
            d.ellipse([20, 20, 44, 44], fill=(255, 255, 255, 200))

        def on_show(icon, item): show_window()
        def on_toggle(icon, item): toggle_clicker()
        def on_quit(icon, item):
            persist_save(); stop_clicker(); icon.stop(); os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem(f"{APP_NAME} {APP_VERSION}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Window", on_show, default=True),
            pystray.MenuItem("Toggle Clicker (F6)", on_toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        )

        _tray_icon = pystray.Icon(APP_NAME, icon_img, APP_NAME, menu)
        _tray_icon.run_detached()
        print("[LexiClicker] Tray started")

    except ImportError:
        print("[LexiClicker] pystray/Pillow not installed — tray disabled")
    except Exception as e:
        print(f"[LexiClicker] Tray error: {e}")

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    load_save()
    bind_hotkeys()
    start_tray()

    FlaskUI(
        app=app,
        server="flask",
        width=state.get('win_w', 1100),
        height=state.get('win_h', 780),
        port=5000,
    ).run()
