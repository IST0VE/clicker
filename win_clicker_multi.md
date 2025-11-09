Окей, попробуем «как на телефонах», но на ПК: чередуем **несколько кнопок мыши** в одном потоке ввода. Если игра засчитывает клики **покомпонентно** (по каждой кнопке свой «дебаунс»), то RR-чередование `left;right` часто поднимает эффективный CPS выше «стены» ~7.

Ниже — обновлённый мульти-кликер под Windows (SendInput, без зависимостей), где можно указать сразу несколько кнопок (`--buttons "left;right;middle"`) и схему выбора (`roundrobin|random|weighted`). Он совместим с мульти-точками/амплитудой и режимом точного CPS (`--rate`), чтобы не «терять» клики.

---

### Файл `win_clicker_multi.py`

Скопируй целиком и запусти.

```python
# -*- coding: utf-8 -*-
# Multi-point & multi-button clicker for Windows using SendInput (no external deps)
import argparse
import ctypes
import os
import random
import sys
import time
from ctypes import wintypes
from typing import List, Tuple

# ---------- WinAPI setup ----------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm", use_last_error=True)

# timer resolution to 1ms (best-effort)
try:
    winmm.timeBeginPeriod(1)
except Exception:
    pass

# Priority boost (HIGH_PRIORITY_CLASS)
HIGH_PRIORITY_CLASS = 0x00000080
try:
    kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), HIGH_PRIORITY_CLASS)
except Exception:
    pass

# constants
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

VK_F8 = 0x77

SM_CXSCREEN = 0
SM_CYSCREEN = 1

# types
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )

class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", wintypes.DWORD),
        ("mi", MOUSEINPUT),
    )

LPINPUT = ctypes.POINTER(INPUT)

user32.SendInput.argtypes = (wintypes.UINT, LPINPUT, ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL

user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short

user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

# DPI awareness (точность абсолютных координат)
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

SCR_W = user32.GetSystemMetrics(SM_CXSCREEN)
SCR_H = user32.GetSystemMetrics(SM_CYSCREEN)

def to_abs(x: int, y: int) -> Tuple[int, int]:
    nx = int(x * 65535 // (SCR_W - 1))
    ny = int(y * 65535 // (SCR_H - 1))
    return nx, ny

# ---------- helpers ----------
def make_mouse_input(flags, dx=0, dy=0, data=0) -> INPUT:
    return INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=ULONG_PTR(0)),
    )

BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

def hotkey_stop_pressed() -> bool:
    return (user32.GetAsyncKeyState(VK_F8) & 0x8000) != 0

def save_progress(path, n):
    if not path:
        return
    try:
        with open(path, "w") as f:
            f.write(str(n))
    except Exception:
        pass

def load_progress(path) -> int:
    if not path or not os.path.exists(path):
        return 0
    try:
        return int(open(path, "r").read().strip() or "0")
    except Exception:
        return 0

def get_cursor_pos() -> Tuple[int, int]:
    pt = POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return 0, 0

# ---------- parsing ----------
def parse_points_str(s: str) -> List[Tuple[int, int]]:
    pts = []
    for part in s.split(";"):
        part = part.strip()
        if not part:
            continue
        x_str, y_str = part.split(",")
        pts.append((int(x_str), int(y_str)))
    if not pts:
        raise ValueError("Не удалось распарсить --points")
    return pts

def parse_int_list(s: str, expected_len: int = None) -> List[int]:
    arr = [int(x.strip()) for x in s.split(";") if x.strip() != ""]
    if expected_len is not None and len(arr) != expected_len:
        raise ValueError(f"Ожидалось {expected_len} значений, получено {len(arr)}")
    return arr

def parse_buttons_str(s: str) -> List[str]:
    btns = [b.strip().lower() for b in s.split(";") if b.strip() != ""]
    allowed = {"left","right","middle"}
    for b in btns:
        if b not in allowed:
            raise ValueError(f"Кнопка '{b}' не поддерживается. Допустимо: left;right;middle")
    if not btns:
        raise ValueError("Список --buttons пуст.")
    return btns

# ---------- schedulers ----------
def make_scheduler(pattern: str, n_items: int, weights: List[int] = None):
    idx = 0
    if pattern == "roundrobin":
        def rr():
            nonlocal idx
            cur = idx
            idx = (idx + 1) % n_items
            return cur
        return rr
    elif pattern == "random":
        def rnd():
            return random.randrange(n_items)
        return rnd
    elif pattern == "weighted":
        if not weights:
            weights = [1] * n_items
        total = float(sum(max(0, w) for w in weights))
        if total <= 0:
            weights = [1] * n_items
            total = float(n_items)
        cum = []
        c = 0.0
        for w in weights:
            c += max(0.0, float(w))
            cum.append(c)
        def wdraw():
            r = random.uniform(0.0, total)
            for i, v in enumerate(cum):
                if r <= v:
                    return i
            return n_items - 1
        return wdraw
    else:
        raise ValueError("Неизвестный pattern")

# ---------- click kernels ----------
def jitter_point(x: int, y: int, amp: int) -> Tuple[int, int]:
    if amp <= 0:
        return x, y
    rx = x + random.randint(-amp, amp)
    ry = y + random.randint(-amp, amp)
    rx = max(0, min(SCR_W - 1, rx))
    ry = max(0, min(SCR_H - 1, ry))
    return rx, ry

def one_click_at_with_button(x: int, y: int, button: str):
    down_flag, up_flag = BUTTON_FLAGS[button]
    ax, ay = to_abs(x, y)
    arr = (INPUT * 3)()
    arr[0] = make_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ax, ay)
    arr[1] = make_mouse_input(down_flag)
    arr[2] = make_mouse_input(up_flag)
    user32.SendInput(3, arr, ctypes.sizeof(INPUT))

# precise wait helper for --rate
def wait_interval(interval: float):
    t_end = time.perf_counter() + interval
    while True:
        now = time.perf_counter()
        if now >= t_end:
            break
        rem = t_end - now
        if rem > 0.002:
            time.sleep(0.001)

def multi_points_rate(points: List[Tuple[int, int]],
                      amps: List[int],
                      count: int,
                      cps: float,
                      point_pattern: str,
                      point_weights: List[int],
                      buttons: List[str],
                      button_pattern: str,
                      button_weights: List[int],
                      progress_every: int,
                      resume_file: str):
    """Точный CPS: по одному клику с выдерживанием интервала, чередуя кнопки."""
    p_sched = make_scheduler(point_pattern, len(points), point_weights)
    b_sched = make_scheduler(button_pattern, len(buttons), button_weights)
    done = load_progress(resume_file)
    i = done
    interval = 1.0 / max(0.001, cps)
    print(f"[rate] {cps:.3f} CPS, points={len(points)}, buttons={buttons}, pt-pattern={point_pattern}, btn-pattern={button_pattern}")
    while i < count:
        if hotkey_stop_pressed():
            print("\n[STOP] F8 pressed.")
            break
        pidx = p_sched()
        bidx = b_sched()
        x, y = points[pidx]
        ax, ay = jitter_point(x, y, amps[pidx])
        btn = buttons[bidx]
        one_click_at_with_button(ax, ay, btn)
        i += 1
        if (i % progress_every == 0) or (i == count):
            print(f"Clicks: {i}/{count}")
            save_progress(resume_file, i)
        wait_interval(interval)
    print("Done (rate).")

def multi_points_batched(points: List[Tuple[int, int]],
                         amps: List[int],
                         count: int,
                         point_pattern: str,
                         point_weights: List[int],
                         buttons: List[str],
                         button_pattern: str,
                         button_weights: List[int],
                         batch: int,
                         progress_every: int,
                         resume_file: str):
    """Максимальная скорость: батчируем move+down/up, чередуя точки и кнопки."""
    p_sched = make_scheduler(point_pattern, len(points), point_weights)
    b_sched = make_scheduler(button_pattern, len(buttons), button_weights)
    done = load_progress(resume_file)
    i = done
    print(f"[batched] max speed, points={len(points)}, buttons={buttons}, pt-pattern={point_pattern}, btn-pattern={button_pattern}, batch={batch}")
    while i < count:
        if hotkey_stop_pressed():
            print("\n[STOP] F8 pressed.")
            break
        cur_clicks = min(batch, count - i)
        n_inputs = cur_clicks * 3
        BufType = INPUT * n_inputs
        buf = BufType()
        idx = 0
        for _ in range(cur_clicks):
            pidx = p_sched()
            bidx = b_sched()
            x, y = points[pidx]
            ax, ay = jitter_point(x, y, amps[pidx])
            mx, my = to_abs(ax, ay)
            down_flag, up_flag = BUTTON_FLAGS[buttons[bidx]]
            buf[idx] = make_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, mx, my); idx += 1
            buf[idx] = make_mouse_input(down_flag); idx += 1
            buf[idx] = make_mouse_input(up_flag); idx += 1
        sent = user32.SendInput(n_inputs, buf, ctypes.sizeof(INPUT))
        if sent != n_inputs:
            pass
        i += cur_clicks
        if (i % progress_every == 0) or (i == count):
            print(f"Clicks: {i}/{count}")
            save_progress(resume_file, i)
    print("Done (batched).")

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Windows multi-point & multi-button clicker (SendInput). Press F8 to stop.")
    group_pts = p.add_mutually_exclusive_group(required=True)
    group_pts.add_argument("--points", type=str,
                           help='Список точек "x1,y1;x2,y2;...". Пример: --points "900,600;950,600;1000,600"')
    group_pts.add_argument("--pick", type=int,
                           help="Интерактивно выбрать N точек: наведите курсор на точку и жмите Enter.")

    # точки/амплитуды/паттерн
    p.add_argument("--pattern", choices=["roundrobin", "random", "weighted"], default="roundrobin",
                   help="Схема обхода точек.")
    p.add_argument("--weights", type=str, default=None,
                   help='Для pattern=weighted: "w1;w2;...". Длина = числу точек.')
    p.add_argument("--amp", type=int, default=0,
                   help="Амплитуда джиттера для всех точек (px).")
    p.add_argument("--amps", type=str, default=None,
                   help='Амплитуды по каждой точке: "a1;a2;...". Перебивает --amp.')

    # кнопки и схема их выбора
    p.add_argument("--buttons", type=str, default="left",
                   help='Кнопки, которыми кликать: "left;right;middle". Пример: --buttons "left;right"')
    p.add_argument("--button-pattern", choices=["roundrobin", "random", "weighted"], default="roundrobin",
                   help="Схема выбора кнопки (если указано несколько).")
    p.add_argument("--button-weights", type=str, default=None,
                   help='Для button-pattern=weighted: "w1;w2;...". Длина = числу кнопок.')

    p.add_argument("--count", type=int, required=True, help="Сколько кликов отправить (суммарно по всем кнопкам).")
    p.add_argument("--rate", type=float, default=None,
                   help="Ограничить частоту (CPS, суммарно). Если не задано — максимальная скорость (батчами).")
    p.add_argument("--batch", type=int, default=8000,
                   help="Размер батча для максимальной скорости (игнорируется с --rate).")
    p.add_argument("--progress-every", type=int, default=1_000_000, help="Шаг логирования прогресса.")
    p.add_argument("--resume-file", type=str, default=None, help="Файл прогресса для продолжения.")
    p.add_argument("--start-delay", type=float, default=3.0, help="Задержка перед стартом (сек).")
    return p.parse_args()

def pick_points(n: int) -> List[Tuple[int, int]]:
    print(f"Интерактивный выбор {n} точек. Наводите курсор и жмите Enter. (F8 — аварийный стоп)")
    pts = []
    for i in range(1, n + 1):
        input(f"[{i}/{n}] Наведите курсор на точку #{i} и нажмите Enter...")
        if hotkey_stop_pressed():
            print("STOP нажатием F8.")
            break
        x, y = get_cursor_pos()
        pts.append((x, y))
        print(f"  → точка #{i}: ({x}, {y})")
    return pts

def main():
    args = parse_args()
    if args.count <= 0:
        print("count должен быть > 0"); sys.exit(1)

    # точки
    if args.points:
        points = parse_points_str(args.points)
    else:
        points = pick_points(args.pick)
        if not points:
            print("Нет точек — выходим.")
            sys.exit(1)

    n = len(points)
    # амплитуды
    if args.amps:
        amps = parse_int_list(args.amps, expected_len=n)
    else:
        amps = [max(0, int(args.amp))] * n
    # веса точек
    pt_weights = None
    if args.pattern == "weighted":
        if args.weights is None:
            pt_weights = [1] * n
        else:
            pt_weights = parse_int_list(args.weights, expected_len=n)

    # кнопки
    buttons = parse_buttons_str(args.buttons)
    # веса кнопок
    btn_weights = None
    if args.button_pattern == "weighted":
        if args.button_weights is None:
            btn_weights = [1] * len(buttons)
        else:
            btn_weights = parse_int_list(args.button_weights, expected_len=len(buttons))

    print("=== Multi-Point & Multi-Button Clicker (SendInput) ===")
    print(f"points={n}, pattern={args.pattern}, amp={args.amp if not args.amps else args.amps}")
    print(f"buttons={buttons}, btn-pattern={args.button_pattern}")
    print(f"count={args.count}, rate={args.rate or 'max'}, batch={args.batch}")
    print("Старт через", args.start_delay, "сек. Нажмите F8 для остановки.")
    time.sleep(args.start_delay)

    try:
        if args.rate and args.rate > 0:
            multi_points_rate(points, amps, args.count, args.rate,
                              args.pattern, pt_weights,
                              buttons, args.button_pattern, btn_weights,
                              args.progress_every, args.resume_file)
        else:
            multi_points_batched(points, amps, args.count,
                                 args.pattern, pt_weights,
                                 buttons, args.button_pattern, btn_weights,
                                 args.batch, args.progress_every, args.resume_file)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user.")
    finally:
        try:
            winmm.timeEndPeriod(1)
        except Exception:
            pass

if __name__ == "__main__":
    main()
```

---

### Как пользоваться

1. **Чередуем LMB и RMB по кругу, ~14 CPS суммарно (≈7 на кнопку):**

```bash
python win_clicker_multi.py ^
  --points "960,540" ^
  --buttons "left;right" ^
  --pattern roundrobin ^
  --button-pattern roundrobin ^
  --rate 14 ^
  --count 1000000
```

> В самой игре повесь **одну и ту же функцию** на ЛКМ и ПКМ. Если игра считает по-кнопочно, это даст прирост.

2. **Три точки + две кнопки, случайный обход, точный лимит:**

```bash
python win_clicker_multi.py ^
  --points "900,600;950,600;1000,600" ^
  --buttons "left;right" ^
  --pattern random ^
  --button-pattern random ^
  --amp 8 ^
  --rate 16 ^
  --count 200000
```

3. **Максимальная скорость батчами (без лимитера), rr по точкам и кнопкам:**

```bash
python win_clicker_multi.py ^
  --pick 2 ^
  --buttons "left;right;middle" ^
  --pattern roundrobin ^
  --button-pattern roundrobin ^
  --amp 5 ^
  --count 5000000 ^
  --batch 12000
```

---

### Пару практических советов

* В игре проверь, что **одно действие можно привязать к двум кнопкам** мыши сразу. Если нет — эта стратегия не сработает.
* Если увидишь «потолок» снова — попробуй ещё и **колесо (middle)**, т.е. `--buttons "left;right;middle"`.
* Поднимай суммарный `--rate` постепенно (12 → 14 → 16…), смотря, сколько реально засчитывает игра. Задача — попасть «в окно» обработки, а не спамить впустую.
* F8 — аварийная остановка.

Если захочешь — добавлю чередование **кнопок + клавиш** (например, `left;right;SPACE`) с таким же round-robin, но это уже зависит от того, позволяет ли игра привязать ту же функцию к клавиатуре.
