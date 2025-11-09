Окей, под Windows лучше уйти от PyAutoGUI и жать мышь напрямую через WinAPI `SendInput` — это на порядок быстрее. Ниже готовый **win-кликер** с двумя режимами:

* **Максимальная скорость (no-move)** — клики в текущей позиции курсора без перемещений (самый быстрый вариант для 250M).
* **Область/точка** — клики в выбранной точке (с амплитудой) или случайно в прямоугольной области. Чуть медленнее из-за движений курсора.

Есть горячая клавиша **F8 — аварийный стоп**, прогресс-файл для резюма, батч-отправка кликов (сильно ускоряет).

---

### Установка

Ничего доп. ставить не нужно — чистый Python 3.x на Windows.

---

### `win_clicker_fast.py`

```python
# -*- coding: utf-8 -*-
# Windows ultra-fast clicker using SendInput (no external deps)
import argparse
import ctypes
import os
import random
import sys
import time
from ctypes import wintypes

# ---------- WinAPI setup ----------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm", use_last_error=True)

# timer resolution to 1ms (best-effort)
winmm.timeBeginPeriod(1)

# Priority boost (HIGH_PRIORITY_CLASS)
HIGH_PRIORITY_CLASS = 0x00000080
kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), HIGH_PRIORITY_CLASS)

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

# DPI awareness (точность абсолютных координат)
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

SCR_W = user32.GetSystemMetrics(SM_CXSCREEN)
SCR_H = user32.GetSystemMetrics(SM_CYSCREEN)

def to_abs(x, y):
    # Normalize to 0..65535 for ABSOLUTE moves
    nx = int(x * 65535 // (SCR_W - 1))
    ny = int(y * 65535 // (SCR_H - 1))
    return nx, ny

# ---------- helpers ----------
def make_mouse_input(flags, dx=0, dy=0, data=0):
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

# ---------- clickers ----------
def click_no_move(count, button, batch, progress_every, resume_file):
    """Fastest mode: no cursor movement, clicks at current position. Batches down/up events."""
    down_flag, up_flag = BUTTON_FLAGS[button]
    # prepare a reusable batch buffer
    max_events = batch * 2
    BufType = INPUT * max_events
    buf = BufType()
    for i in range(0, max_events, 2):
        buf[i] = make_mouse_input(down_flag)
        buf[i + 1] = make_mouse_input(up_flag)

    done = load_progress(resume_file)
    i = done
    while i < count:
        if hotkey_stop_pressed():
            print("\n[STOP] F8 pressed.")
            break
        remaining = count - i
        cur_clicks = batch if remaining >= batch else remaining
        n_inputs = cur_clicks * 2
        sent = user32.SendInput(n_inputs, buf, ctypes.sizeof(INPUT))
        if sent != n_inputs:
            # best effort: try partial progress
            pass
        i += cur_clicks
        if (i % progress_every == 0) or (i == count):
            print(f"Clicks: {i}/{count}")
            save_progress(resume_file, i)
    print("Done (no-move).")

def click_point(count, x, y, amplitude, button, batch, progress_every, resume_file):
    """Point + amplitude. If amplitude=0 we can pre-move once and then use no-move batching."""
    if amplitude <= 0:
        user32.SetCursorPos(int(x), int(y))
        return click_no_move(count, button, batch, progress_every, resume_file)

    down_flag, up_flag = BUTTON_FLAGS[button]
    done = load_progress(resume_file)
    i = done
    while i < count:
        if hotkey_stop_pressed():
            print("\n[STOP] F8 pressed.")
            break
        # micro-batch with movement per click (slower than no-move)
        cur_clicks = min(batch, count - i)
        n_inputs = cur_clicks * 3  # move + down + up per click
        BufType = INPUT * n_inputs
        buf = BufType()
        idx = 0
        for _ in range(cur_clicks):
            rx = x + random.randint(-amplitude, amplitude)
            ry = y + random.randint(-amplitude, amplitude)
            ax, ay = to_abs(max(0, min(SCR_W - 1, rx)), max(0, min(SCR_H - 1, ry)))
            buf[idx] = make_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ax, ay); idx += 1
            buf[idx] = make_mouse_input(down_flag); idx += 1
            buf[idx] = make_mouse_input(up_flag); idx += 1
        sent = user32.SendInput(n_inputs, buf, ctypes.sizeof(INPUT))
        if sent != n_inputs:
            pass
        i += cur_clicks
        if (i % progress_every == 0) or (i == count):
            print(f"Clicks: {i}/{count}")
            save_progress(resume_file, i)
    print("Done (point).")

def click_area(count, x1, y1, x2, y2, button, batch, progress_every, resume_file):
    """Random point inside rectangle per click (batched)."""
    left, right = sorted([int(x1), int(x2)])
    top, bottom = sorted([int(y1), int(y2)])
    down_flag, up_flag = BUTTON_FLAGS[button]

    done = load_progress(resume_file)
    i = done
    while i < count:
        if hotkey_stop_pressed():
            print("\n[STOP] F8 pressed.")
            break
        cur_clicks = min(batch, count - i)
        n_inputs = cur_clicks * 3  # move + down + up per click
        BufType = INPUT * n_inputs
        buf = BufType()
        idx = 0
        for _ in range(cur_clicks):
            rx = random.randint(left, right)
            ry = random.randint(top, bottom)
            ax, ay = to_abs(rx, ry)
            buf[idx] = make_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ax, ay); idx += 1
            buf[idx] = make_mouse_input(down_flag); idx += 1
            buf[idx] = make_mouse_input(up_flag); idx += 1
        sent = user32.SendInput(n_inputs, buf, ctypes.sizeof(INPUT))
        if sent != n_inputs:
            pass
        i += cur_clicks
        if (i % progress_every == 0) or (i == count):
            print(f"Clicks: {i}/{count}")
            save_progress(resume_file, i)
    print("Done (area).")

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Windows ultra-fast clicker (SendInput). Press F8 to stop.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--no-move", action="store_true",
                      help="Максимальная скорость: клики без перемещений (в текущей позиции).")
    mode.add_argument("--point", nargs=2, type=int, metavar=("X", "Y"),
                      help="Кликать вокруг точки (см. --amplitude). При amplitude=0 курсор переместится один раз.")
    mode.add_argument("--area", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"),
                      help="Случайные точки внутри прямоугольника.")
    p.add_argument("--amplitude", type=int, default=0, help="Амплитуда случайного смещения (для --point).")
    p.add_argument("--count", type=int, required=True, help="Сколько кликов выполнить (например, 250000000).")
    p.add_argument("--button", choices=["left", "right", "middle"], default="left", help="Кнопка мыши.")
    p.add_argument("--batch", type=int, default=10000,
                   help="Размер батча (сколько кликов отправлять одним SendInput). 5k–50k обычно ок.")
    p.add_argument("--progress-every", type=int, default=1_000_000,
                   help="Как часто печатать прогресс и сохранять резюме (в кликах).")
    p.add_argument("--resume-file", type=str, default=None, help="Файл прогресса для продолжения.")
    p.add_argument("--start-delay", type=float, default=3.0, help="Задержка перед стартом (сек).")
    return p.parse_args()

def main():
    args = parse_args()
    if args.count <= 0:
        print("count должен быть > 0"); sys.exit(1)

    print("=== Windows Clicker (SendInput) ===")
    if args.no_move:
        print(f"Mode: NO-MOVE | count={args.count}, button={args.button}, batch={args.batch}")
    elif args.point:
        x, y = args.point
        print(f"Mode: POINT | point=({x},{y}), amp={args.amplitude}, count={args.count}, button={args.button}, batch={args.batch}")
    else:
        x1, y1, x2, y2 = args.area
        print(f"Mode: AREA | ({x1},{y1})-({x2},{y2}), count={args.count}, button={args.button}, batch={args.batch}")
    print("Start in", args.start_delay, "s. Press F8 anytime to stop.")
    time.sleep(args.start_delay)

    try:
        if args.no_move:
            click_no_move(args.count, args.button, args.batch, args.progress_every, args.resume_file)
        elif args.point:
            x, y = args.point
            click_point(args.count, x, y, args.amplitude, args.button, args.batch, args.progress_every, args.resume_file)
        else:
            x1, y1, x2, y2 = args.area
            click_area(args.count, x1, y1, x2, y2, args.button, args.batch, args.progress_every, args.resume_file)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user.")
    finally:
        # best-effort cleanup
        try:
            winmm.timeEndPeriod(1)
        except Exception:
            pass

if __name__ == "__main__":
    main()
```

---

### Как запустить максимально быстро на 250 000 000 кликов

1. Наведи курсор туда, где нужно кликать.
2. Запусти без перемещений (самый быстрый режим):

```bash
python win_clicker_fast.py --no-move --count 250000000 --batch 20000 --progress-every 5000000 --resume-file clicks.state --start-delay 5
```

> `--batch` можно поднять (например, 50000), если система тянет. Слишком большой батч может упираться в лимиты драйвера — начинай с 10–20k.

### Варианты

* Кликать вокруг точки с разбросом 15px:

```bash
python win_clicker_fast.py --point 900 600 --amplitude 15 --count 10000000 --batch 10000
```

* Случайно по области:

```bash
python win_clicker_fast.py --area 100 200 600 700 --count 5000000 --batch 8000
```

### Замечания и безопасность

* **F8 = стоп** на любом этапе.
* Игра/ПО могут трактовать автокликер как чит — используй на свой риск.
* Отключи засыпание/блокировку экрана.
* Режим **no-move** быстрее остальных; область/амплитуда замедляют из-за генерации координат и перемещений курсора.

Если нужно, могу добавить **горячие клавиши старт/пауза**, таргет по названию окна, или «кадровый лимитер» (клики не чаще N/сек), но для *максимальной* скорости текущая реализация — топ.
