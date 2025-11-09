import argparse
import random
import time
import sys
from typing import Tuple, Optional

import pyautogui

pyautogui.FAILSAFE = True  # двиньте мышь в левый верхний угол — мгновенная остановка


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Простой автокликер: область ИЛИ точка+амплитуда. Экстренный стоп — мышь в левый верхний угол."
    )

    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--area", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"),
                      help="Координаты прямоугольника (две точки). Клик случайно внутри области.")
    mode.add_argument("--point", nargs=2, type=int, metavar=("X", "Y"),
                      help="Целевая точка. Используйте --amplitude для случайного смещения вокруг неё.")
    p.add_argument("--pick-area", action="store_true",
                   help="Интерактивно выбрать область: наведите курсор на углы по подсказке.")
    p.add_argument("--pick-point", action="store_true",
                   help="Интерактивно выбрать точку: наведите курсор по подсказке.")

    p.add_argument("--count", type=int, required=True, help="Сколько кликов выполнить (например, 100).")
    speed = p.add_mutually_exclusive_group(required=False)
    speed.add_argument("--interval", type=float, default=None,
                       help="Базовый интервал между кликами в секундах (например, 0.1).")
    speed.add_argument("--cps", type=float, default=None,
                       help="Clicks per second — кликов в секунду (например, 12.5). Эквивалент 1/cps.")
    p.add_argument("--interval-jitter", type=float, default=0.0,
                   help="Макс. добавочная случайная задержка ±jitter к интервалу (сек).")

    p.add_argument("--amplitude", type=int, default=0,
                   help="Амплитуда случайного смещения в пикселях (для режима --point).")
    p.add_argument("--button", choices=["left", "right", "middle"], default="left",
                   help="Кнопка мыши (по умолчанию left).")
    p.add_argument("--start-delay", type=float, default=3.0,
                   help="Задержка перед стартом (сек) чтобы успеть переключиться в нужное окно.")
    p.add_argument("--move-first", action="store_true",
                   help="Перед каждым кликом перемещать курсор (по умолчанию PyAutoGUI кликает в текущую позицию; "
                        "в режиме area/point курсор и так будет перемещён).")

    args = p.parse_args()

    if args.cps is not None:
        if args.cps <= 0:
            p.error("--cps должен быть > 0")
        args.interval = 1.0 / args.cps
    if args.interval is None:
        # по умолчанию 10 кликов/сек, если не задано ничего
        args.interval = 0.1

    if args.interval < 0:
        p.error("--interval не может быть отрицательным")
    if args.interval_jitter < 0:
        p.error("--interval-jitter не может быть отрицательным")

    if not args.area and not args.point and not args.pick_area and not args.pick_point:
        p.error("Укажите область (--area/--pick-area) ИЛИ точку (--point/--pick-point).")

    if (args.area or args.pick_area) and (args.point or args.pick_point):
        p.error("Выберите только один режим: область ИЛИ точка.")

    if args.count <= 0:
        p.error("--count должен быть > 0")

    return args


def prompt_pick_point(prompt: str) -> Tuple[int, int]:
    print(prompt)
    print("Наведите курсор и нажмите Enter в этой консоли...")
    try:
        input()
    except KeyboardInterrupt:
        sys.exit(0)
    x, y = pyautogui.position()
    print(f"→ Зафиксирована точка: ({x}, {y})")
    return x, y


def prompt_pick_area() -> Tuple[int, int, int, int]:
    print("Выбор области:")
    x1, y1 = prompt_pick_point("Шаг 1/2: наведите курсор на ЛЕВЫЙ-ВЕРХНИЙ угол области.")
    x2, y2 = prompt_pick_point("Шаг 2/2: наведите курсор на ПРАВЫЙ-НИЖНИЙ угол области.")
    # нормализуем
    left, right = sorted([x1, x2])
    top, bottom = sorted([y1, y2])
    print(f"→ Область: ({left}, {top}) — ({right}, {bottom}) [w={right-left}, h={bottom-top}]")
    return left, top, right, bottom


def random_point_in_area(area: Tuple[int, int, int, int]) -> Tuple[int, int]:
    x1, y1, x2, y2 = area
    x = random.randint(x1, x2)
    y = random.randint(y1, y2)
    return x, y


def jitter_around_point(point: Tuple[int, int], amplitude: int) -> Tuple[int, int]:
    if amplitude <= 0:
        return point
    x, y = point
    dx = random.randint(-amplitude, amplitude)
    dy = random.randint(-amplitude, amplitude)
    return x + dx, y + dy


def sleep_with_jitter(base_interval: float, jitter: float):
    if jitter <= 0:
        time.sleep(base_interval)
        return
    # равномерно в диапазоне [base-jitter, base+jitter], но не ниже нуля
    wait = max(0.0, base_interval + random.uniform(-jitter, jitter))
    time.sleep(wait)


def main():
    args = parse_args()

    # Определяем режим и координаты
    area: Optional[Tuple[int, int, int, int]] = None
    point: Optional[Tuple[int, int]] = None

    if args.pick_area:
        area = prompt_pick_area()
    elif args.area:
        x1, y1, x2, y2 = args.area
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        area = (left, top, right, bottom)

    if args.pick_point:
        point = prompt_pick_point("Выбор точки для кликов.")
    elif args.point:
        point = (args.point[0], args.point[1])

    # Мини-сводка
    if area:
        mode_desc = f"Режим: ОБЛАСТЬ {area}"
    else:
        mode_desc = f"Режим: ТОЧКА {point} + амплитуда {args.amplitude}px"

    print("\n================= АВТОКЛИКЕР =================")
    print(mode_desc)
    print(f"Кликов: {args.count}, интервал: {args.interval}s, jitter: ±{args.interval_jitter}s, кнопка: {args.button}")
    print(f"Старт через {args.start_delay} сек... Уведите курсор в левый верхний угол для аварийной остановки.")
    time.sleep(args.start_delay)

    try:
        for i in range(1, args.count + 1):
            if area:
                x, y = random_point_in_area(area)
                pyautogui.moveTo(x, y)
            else:
                x, y = jitter_around_point(point, args.amplitude)
                pyautogui.moveTo(x, y)

            pyautogui.click(button=args.button)

            # опционально — «дожимать» перемещение перед следующим кликом
            if args.move_first:
                pyautogui.moveTo(x, y)

            if i % 50 == 0 or i == args.count:
                print(f"Сделано кликов: {i}/{args.count}")

            sleep_with_jitter(args.interval, args.interval_jitter)

        print("Готово.")
    except pyautogui.FailSafeException:
        print("\n[ОСТАНОВЛЕНО] Сработал failsafe (мышь в левом верхнем углу).")
    except KeyboardInterrupt:
        print("\n[ОСТАНОВЛЕНО] Пользователь прервал выполнение (Ctrl+C).")


if __name__ == "__main__":
    main()
