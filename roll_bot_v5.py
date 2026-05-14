import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pyautogui
import pytesseract

try:
    import keyboard
except ImportError:
    keyboard = None


BASE_DIR = Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config.json"
TARGETS_PATH = BASE_DIR / "targets.json"
TEMPLATES_PATH = BASE_DIR / "templates.json"

DEBUG_DIR = BASE_DIR / "debug"
LOGS_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"

DEBUG_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)


DEFAULT_CONFIG = {
    "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    "ocr_languages": "rus+eng",

    "left_button": [1091, 715],
    "right_button": [1295, 714],

    "ocr_regions": {
        "stat_name": [1120, 405, 170, 35],
        "stat_value": [1250, 405, 100, 35]
    },

    "wait_after_clear": 1.0,
    "wait_after_ignore": 1.0,
    "wait_after_exchange": 1.0,

    "max_attempts": 1000,
    "debug": True,
    "dry_run": False,

    "template_match_threshold": 0.72,
    "template_scale": 6,

    "fast_mode": False,
    "debug_during_bot": False,
    "template_cache_enabled": True,
    "tesseract_timeout": 1.5,
    "pyautogui_pause": 0.05
}


DEFAULT_TARGETS = {
    "targets": [
        {
            "id": "agility_3000",
            "name": "Ловкость 3000+",
            "stat_text": "Ловкость",
            "value": 3000.0,
            "value_mode": "greater_or_equal"
        },
        {
            "id": "speed_75000",
            "name": "Скорость 75000",
            "stat_text": "Скорость",
            "value": 75000.0,
            "value_mode": "exact"
        }
    ]
}


DEFAULT_TEMPLATES = {
    "templates": []
}


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class BotControl:
    def __init__(self):
        self.paused = False
        self.stopped = False
        self.hotkeys_registered = False

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            print("\n[HOTKEY] Paused. Press F8 to continue, F9 or ESC to stop.")
        else:
            print("\n[HOTKEY] Resumed.")

    def request_stop(self):
        self.stopped = True
        print("\n[HOTKEY] Stop requested.")

    def register_hotkeys(self):
        if keyboard is None:
            print("Hotkeys disabled: package 'keyboard' is not installed.")
            print("Install it with: python -m pip install keyboard")
            print("You can still stop with Ctrl+C or PyAutoGUI failsafe top-left corner.")
            return

        try:
            keyboard.add_hotkey("f8", self.toggle_pause)
            keyboard.add_hotkey("f9", self.request_stop)
            keyboard.add_hotkey("esc", self.request_stop)
            self.hotkeys_registered = True
            print("Hotkeys: F8 pause/resume | F9 stop | ESC stop")
        except Exception as exc:
            print(f"Hotkeys disabled: {exc}")
            print("You can still stop with Ctrl+C or PyAutoGUI failsafe top-left corner.")

    def unregister_hotkeys(self):
        if keyboard is None or not self.hotkeys_registered:
            return

        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        self.hotkeys_registered = False

    def should_stop(self):
        return self.stopped

    def wait_if_paused(self):
        printed = False
        while self.paused and not self.stopped:
            if not printed:
                print("Paused. Press F8 to continue, F9 or ESC to stop.")
                printed = True
            time.sleep(0.1)

        return not self.stopped


def sleep_with_control(seconds, control=None):
    end_time = time.time() + float(seconds)

    while time.time() < end_time:
        if control is not None:
            if control.should_stop():
                return False
            if not control.wait_if_paused():
                return False

        time.sleep(min(0.05, max(0.0, end_time - time.time())))

    return True


def load_json(path, default_data):
    if not path.exists():
        save_json(path, default_data)
        return default_data

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        print(f"Failed to read {path}. Using defaults.")
        return default_data


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def now_string():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def safe_filename(text):
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
        "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch",
        "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
        "і": "i", "ї": "yi", "є": "ye"
    }

    result = ""
    for ch in text.lower():
        result += mapping.get(ch, ch)

    result = re.sub(r"[^a-z0-9]+", "_", result)
    result = result.strip("_")

    if not result:
        result = "template"

    return result


def normalize_region(region):
    x, y, w, h = region
    return int(x), int(y), int(w), int(h)


def capture_region(region):
    region = normalize_region(region)
    screenshot = pyautogui.screenshot(region=region)
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def get_stat_region(config):
    return config["ocr_regions"]["stat_name"]


def get_value_region(config):
    return config["ocr_regions"]["stat_value"]


def click_position(position, dry_run=False, label=""):
    x, y = int(position[0]), int(position[1])

    if dry_run:
        print(f"[DRY RUN] Would click {label}: ({x}, {y})")
        return

    pyautogui.click(x, y)


def click_left(config):
    click_position(config["left_button"], config.get("dry_run", False), "LEFT / CLEAR / EXCHANGE")


def click_right(config):
    click_position(config["right_button"], config.get("dry_run", False), "RIGHT / IGNORE / RETURN")


def preprocess_value_image(img, config=None):
    """
    Базова обробка числа для сумісності.
    Основна логіка OCR нижче пробує кілька варіантів картинки.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
    return thresh


def extract_value_from_text(raw_text):
    """
    Дістає число з OCR-тексту без автокорекції.
    150 залишається 150.0, а не перетворюється на 15.0.
    """
    if not raw_text:
        return None

    text = raw_text.replace(",", ".")
    text = text.replace(" ", "")
    text = text.replace("%", "")

    match = re.search(r"\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def create_value_ocr_variants(img, config=None, fast=False):
    """
    Створює варіанти картинки для OCR числа.
    fast=True використовується під час автозапуску, щоб не робити надто багато OCR-викликів.
    fast=False використовується в Test recognition для глибшої перевірки.
    """
    if config is None:
        config = {}

    value_ocr_config = config.get("value_ocr", {})
    hsv_lower = value_ocr_config.get("hsv_lower_gold", [10, 25, 40])
    hsv_upper = value_ocr_config.get("hsv_upper_gold", [50, 255, 255])

    variants = []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    old_big = cv2.resize(gray, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
    _, old_big = cv2.threshold(old_big, 140, 255, cv2.THRESH_BINARY)
    variants.append(("old_threshold_big", old_big))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    clahe_img = clahe.apply(gray)
    clahe_img = cv2.resize(clahe_img, None, fx=8, fy=8, interpolation=cv2.INTER_CUBIC)
    _, clahe_thresh = cv2.threshold(
        clahe_img,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    variants.append(("clahe_otsu", clahe_thresh))

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_gold = np.array(hsv_lower, dtype=np.uint8)
    upper_gold = np.array(hsv_upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_gold, upper_gold)

    if cv2.countNonZero(mask) >= 5:
        kernel = np.ones((2, 2), np.uint8)
        mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        mask_big = cv2.resize(
            mask_closed,
            None,
            fx=6,
            fy=6,
            interpolation=cv2.INTER_NEAREST
        )
        variants.append(("gold_mask_white_on_black", mask_big))
        variants.append(("gold_mask_black_on_white", 255 - mask_big))

        ys, xs = np.where(mask_closed > 0)
        if len(xs) > 0 and len(ys) > 0:
            padding = 4
            x1 = max(0, xs.min() - padding)
            y1 = max(0, ys.min() - padding)
            x2 = min(mask_closed.shape[1], xs.max() + padding + 1)
            y2 = min(mask_closed.shape[0], ys.max() + padding + 1)

            cropped = mask_closed[y1:y2, x1:x2]
            cropped = cv2.copyMakeBorder(
                cropped,
                6, 6, 6, 6,
                cv2.BORDER_CONSTANT,
                value=0
            )
            cropped_big = cv2.resize(
                cropped,
                None,
                fx=7,
                fy=7,
                interpolation=cv2.INTER_NEAREST
            )
            variants.append(("gold_mask_cropped_white_on_black", cropped_big))
            variants.append(("gold_mask_cropped_black_on_white", 255 - cropped_big))

    if fast:
        preferred = {
            "old_threshold_big",
            "clahe_otsu",
            "gold_mask_white_on_black",
            "gold_mask_black_on_white",
        }
        return [(name, img_) for name, img_ in variants if name in preferred]

    raw_gray_big = cv2.resize(gray, None, fx=8, fy=8, interpolation=cv2.INTER_CUBIC)
    raw_gray_big = cv2.copyMakeBorder(
        raw_gray_big,
        10, 10, 10, 10,
        cv2.BORDER_CONSTANT,
        value=255
    )
    variants.insert(0, ("raw_gray_big", raw_gray_big))

    old = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, old = cv2.threshold(old, 140, 255, cv2.THRESH_BINARY)
    variants.append(("old_threshold", old))

    otsu_source = cv2.resize(gray, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(otsu_source, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))
    variants.append(("otsu_inverted", 255 - otsu))

    adaptive_source = cv2.resize(gray, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    adaptive = cv2.adaptiveThreshold(
        adaptive_source,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5
    )
    variants.append(("adaptive", adaptive))
    variants.append(("adaptive_inverted", 255 - adaptive))
    variants.append(("clahe_otsu_inverted", 255 - clahe_thresh))

    return variants


def read_value(config, debug_prefix=None, fast=False):
    img = capture_region(get_value_region(config))
    timestamp = now_string()

    save_debug = bool(debug_prefix) and bool(config.get("debug", True))

    if save_debug:
        cv2.imwrite(str(DEBUG_DIR / f"{debug_prefix}_value_raw_{timestamp}.png"), img)

    variants = create_value_ocr_variants(img, config, fast=fast)

    if fast:
        tess_configs = [
            r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.,%"
        ]
    else:
        tess_configs = [
            r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.,%",
            r"--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.,%",
            r"--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789.,%"
        ]

    timeout = float(config.get("tesseract_timeout", 1.5))
    results = []

    for variant_name, processed in variants:
        if save_debug:
            cv2.imwrite(
                str(DEBUG_DIR / f"{debug_prefix}_value_{variant_name}_{timestamp}.png"),
                processed
            )

        for config_index, tess_config in enumerate(tess_configs, start=1):
            try:
                raw_text = pytesseract.image_to_string(
                    processed,
                    lang="eng",
                    config=tess_config,
                    timeout=timeout
                ).strip()
            except RuntimeError:
                raw_text = ""
            except Exception:
                raw_text = ""

            value = extract_value_from_text(raw_text)

            results.append({
                "variant": f"{variant_name}_psm{config_index}",
                "raw_text": raw_text,
                "value": value,
                "processed": processed
            })

    for result in results:
        raw = result["raw_text"].replace(",", ".")
        if result["value"] is not None and "." in raw:
            return result["value"], result["raw_text"], result["processed"]

    for result in results:
        if result["value"] is not None:
            return result["value"], result["raw_text"], result["processed"]

    raw_joined = " | ".join(result["raw_text"] for result in results if result["raw_text"])
    fallback_processed = variants[0][1] if variants else img
    return None, raw_joined, fallback_processed


def crop_to_content(mask, padding=4):
    ys, xs = np.where(mask > 0)

    if len(xs) < 5 or len(ys) < 5:
        return mask

    x1 = max(0, xs.min() - padding)
    y1 = max(0, ys.min() - padding)
    x2 = min(mask.shape[1], xs.max() + padding)
    y2 = min(mask.shape[0], ys.max() + padding)

    cropped = mask[y1:y2, x1:x2]

    if cropped.size == 0:
        return mask

    return cropped


def preprocess_stat_for_template(img, config):
    """
    Робить з картинки тексту бінарний шаблон:
    - знаходить золотий текст через HSV;
    - прибирає фон;
    - обрізає зайве;
    - збільшує картинку.
    """

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Діапазон для золотого / жовтого тексту.
    # Якщо шаблони погано створюються, ці значення можна буде підкрутити.
    lower_gold = np.array([10, 35, 50], dtype=np.uint8)
    upper_gold = np.array([45, 255, 255], dtype=np.uint8)

    mask = cv2.inRange(hsv, lower_gold, upper_gold)

    kernel = np.ones((2, 2), np.uint8)

    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.medianBlur(mask, 3)

    mask = crop_to_content(mask, padding=5)

    scale = int(config.get("template_scale", 6))
    scale = max(2, min(scale, 12))

    mask = cv2.resize(
        mask,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_NEAREST
    )

    _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)

    return mask


def save_current_stat_template(config, templates_db):
    print("\n=== Save current stat as template ===")
    stat_name = input("Enter stat name exactly as target, for example Физ. Атака: ").strip()

    if not stat_name:
        print("Empty stat name. Cancelled.")
        return

    img = capture_region(get_stat_region(config))
    processed = preprocess_stat_for_template(img, config)

    timestamp = now_string()
    slug = safe_filename(stat_name)

    raw_name = f"{slug}_{timestamp}_raw.png"
    template_name = f"{slug}_{timestamp}.png"

    raw_path = TEMPLATES_DIR / raw_name
    template_path = TEMPLATES_DIR / template_name

    cv2.imwrite(str(raw_path), img)
    cv2.imwrite(str(template_path), processed)

    relative_template_path = str(template_path.relative_to(BASE_DIR)).replace("\\", "/")

    templates_db["templates"].append({
        "stat_text": stat_name,
        "file": relative_template_path,
        "created_at": timestamp
    })

    save_json(TEMPLATES_PATH, templates_db)

    print(f"Template saved for: {stat_name}")
    print(f"Template file: {relative_template_path}")
    print("Important: save 2-3 templates for one stat if recognition is unstable.")


def foreground_ratio(img):
    if img is None or img.size == 0:
        return 0.0

    return float(np.count_nonzero(img)) / float(img.size)


def compare_template(current_processed, template_img):
    if current_processed is None or template_img is None:
        return 0.0

    if current_processed.size == 0 or template_img.size == 0:
        return 0.0

    current_ratio = foreground_ratio(current_processed)
    template_ratio = foreground_ratio(template_img)

    # Якщо після обробки картинка майже порожня — не довіряємо збігу.
    if current_ratio < 0.01 or template_ratio < 0.01:
        return 0.0

    # Якщо картинка майже повністю заповнена — теж не довіряємо.
    if current_ratio > 0.85 or template_ratio > 0.85:
        return 0.0

    try:
        resized_current = cv2.resize(
            current_processed,
            (template_img.shape[1], template_img.shape[0]),
            interpolation=cv2.INTER_NEAREST
        )
    except Exception:
        return 0.0

    # Порівнюємо тільки через absdiff, без cv2.TM_CCOEFF_NORMED,
    # бо TM_CCOEFF_NORMED може давати 1.0 для поганих/майже порожніх масок.
    try:
        diff = cv2.absdiff(resized_current, template_img)
        score = 1.0 - (float(np.mean(diff)) / 255.0)
    except Exception:
        return 0.0

    # Додатковий штраф, якщо кількість "текстових" пікселів дуже різна.
    current_ratio = foreground_ratio(resized_current)
    template_ratio = foreground_ratio(template_img)

    ratio_diff = abs(current_ratio - template_ratio)
    score -= ratio_diff * 2.0

    if score < 0.0:
        score = 0.0

    if score > 1.0:
        score = 1.0

    return score


def build_template_cache(templates_db):
    cache = []

    for item in templates_db.get("templates", []):
        template_file = item.get("file")
        stat_text = item.get("stat_text")

        if not template_file or not stat_text:
            continue

        template_path = BASE_DIR / template_file

        if not template_path.exists():
            continue

        template_img = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)

        if template_img is None:
            continue

        cache.append({
            "stat_text": stat_text,
            "file": template_file,
            "image": template_img
        })

    return cache


def detect_stat_by_template(config, templates_db, debug_prefix=None, template_cache=None):
    img = capture_region(get_stat_region(config))
    current_processed = preprocess_stat_for_template(img, config)

    if debug_prefix and config.get("debug", True):
        timestamp = now_string()
        cv2.imwrite(str(DEBUG_DIR / f"{debug_prefix}_stat_raw_{timestamp}.png"), img)
        cv2.imwrite(str(DEBUG_DIR / f"{debug_prefix}_stat_processed_{timestamp}.png"), current_processed)

    if template_cache is not None:
        template_items = template_cache
    else:
        template_items = []
        for item in templates_db.get("templates", []):
            template_file = item.get("file")
            stat_text = item.get("stat_text")

            if not template_file or not stat_text:
                continue

            template_path = BASE_DIR / template_file

            if not template_path.exists():
                continue

            template_img = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)

            if template_img is None:
                continue

            template_items.append({
                "stat_text": stat_text,
                "file": template_file,
                "image": template_img
            })

    if not template_items:
        return {
            "stat_text": None,
            "score": 0.0,
            "template_file": None,
            "all_scores": [],
            "processed": current_processed
        }

    best_stat = None
    best_score = 0.0
    best_file = None
    all_scores = []

    for item in template_items:
        stat_text = item.get("stat_text")
        template_file = item.get("file")
        template_img = item.get("image")

        if template_img is None or not stat_text:
            continue

        score = compare_template(current_processed, template_img)

        all_scores.append({
            "stat_text": stat_text,
            "file": template_file,
            "score": score
        })

        if score > best_score:
            best_score = score
            best_stat = stat_text
            best_file = template_file

    all_scores.sort(key=lambda x: x["score"], reverse=True)

    return {
        "stat_text": best_stat,
        "score": best_score,
        "template_file": best_file,
        "all_scores": all_scores,
        "processed": current_processed
    }


def read_roll(config, templates_db, debug_prefix=None, template_cache=None, fast=False):
    stat_result = detect_stat_by_template(
        config,
        templates_db,
        debug_prefix=debug_prefix,
        template_cache=template_cache
    )
    value, value_raw, value_processed = read_value(
        config,
        debug_prefix=debug_prefix,
        fast=fast
    )

    return {
        "detected_stat": stat_result["stat_text"],
        "template_score": stat_result["score"],
        "template_file": stat_result["template_file"],
        "all_template_scores": stat_result["all_scores"],
        "value": value,
        "value_raw": value_raw
    }


def match_value(current_value, target):
    if current_value is None:
        return False

    mode = target.get("value_mode", "exact")

    if mode == "exact":
        target_value = float(target["value"])
        return abs(current_value - target_value) < 0.001

    if mode == "greater_or_equal":
        return current_value >= float(target["value"])

    if mode == "greater":
        return current_value > float(target["value"])

    if mode == "less_or_equal":
        return current_value <= float(target["value"])

    if mode == "less":
        return current_value < float(target["value"])

    if mode == "range":
        min_value = float(target["min_value"])
        max_value = float(target["max_value"])
        return min_value <= current_value <= max_value

    return False


def is_target_matched(roll_data, target, config):
    threshold = float(target.get(
        "template_threshold",
        config.get("template_match_threshold", 0.72)
    ))

    detected_stat = roll_data["detected_stat"]
    template_score = roll_data["template_score"]

    text_ok = (
        detected_stat == target["stat_text"]
        and template_score >= threshold
    )

    value_ok = match_value(roll_data["value"], target)

    print(f"Detected stat: {detected_stat}")
    print(f"Template score: {template_score:.4f}")
    print(f"Template file: {roll_data['template_file']}")
    print(f"Target stat: {target['stat_text']}")
    print(f"Template threshold: {threshold}")
    print(f"OCR value raw: {repr(roll_data['value_raw'])}")
    print(f"Parsed value: {roll_data['value']}")
    print(f"Text OK: {text_ok}")
    print(f"Value OK: {value_ok}")

    return text_ok and value_ok


def show_top_template_scores(roll_data, limit=5):
    scores = roll_data.get("all_template_scores", [])

    if not scores:
        print("No templates found. Save templates first.")
        return

    print("\nTop template scores:")
    for item in scores[:limit]:
        print(f"- {item['stat_text']} | score={item['score']:.4f} | file={item['file']}")


def test_recognition(config, targets_db, templates_db, current_target):
    print("\n=== Recognition Test ===")

    template_cache = build_template_cache(templates_db) if config.get("template_cache_enabled", True) else None
    roll_data = read_roll(
        config,
        templates_db,
        debug_prefix="test",
        template_cache=template_cache,
        fast=False
    )

    print(f"Detected stat: {roll_data['detected_stat']}")
    print(f"Template score: {roll_data['template_score']:.4f}")
    print(f"Template file: {roll_data['template_file']}")
    print(f"OCR value raw: {repr(roll_data['value_raw'])}")
    print(f"Parsed value: {roll_data['value']}")

    show_top_template_scores(roll_data)

    print(f"\nDebug images saved to: {DEBUG_DIR}")

    if current_target is not None:
        print("\nTarget check:")
        result = is_target_matched(roll_data, current_target, config)
        print(f"Match result: {result}")


def start_bot(config, targets_db, templates_db, current_target):
    if current_target is None:
        print("No target selected.")
        return

    pyautogui.PAUSE = float(config.get("pyautogui_pause", 0.05))

    control = BotControl()
    control.register_hotkeys()

    template_cache = build_template_cache(templates_db) if config.get("template_cache_enabled", True) else None
    if template_cache is not None:
        print(f"Loaded templates into memory: {len(template_cache)}")

    # Important:
    # Start bot must use the same full OCR pipeline as Test recognition.
    # This keeps real behavior consistent with tests and avoids extra OCR mistakes.
    fast_mode = False
    debug_during_bot = bool(config.get("debug_during_bot", False))

    print("\n=== Start bot ===")
    print(f"Selected target: {current_target['name']}")
    print("Emergency stop: move mouse to the top-left corner.")
    print("Console stop: Ctrl+C")
    print("Hotkeys: F8 pause/resume | F9 stop | ESC stop")
    print("OCR mode: full, same as Test recognition")
    print(f"Debug during bot: {debug_during_bot}")
    print("Start in 3 seconds.")

    try:
        if not sleep_with_control(3, control):
            print("Stopped before start.")
            return

        max_attempts = int(config.get("max_attempts", 1000))

        for attempt in range(1, max_attempts + 1):
            if control.should_stop():
                print("Stopped by hotkey.")
                return

            if not control.wait_if_paused():
                print("Stopped while paused.")
                return

            print(f"\nAttempt #{attempt}")

            click_left(config)
            if not sleep_with_control(float(config.get("wait_after_clear", 1.0)), control):
                print("Stopped after CLEAR.")
                return

            debug_prefix = f"attempt_{attempt}" if debug_during_bot else None
            roll_data = read_roll(
                config,
                templates_db,
                debug_prefix=debug_prefix,
                template_cache=template_cache,
                fast=fast_mode
            )

            matched = is_target_matched(roll_data, current_target, config)

            if matched:
                print("Target found. Clicking EXCHANGE.")
                click_left(config)
                sleep_with_control(float(config.get("wait_after_exchange", 1.0)), control)
                print("Done.")
                return

            print("Not matched. Clicking IGNORE.")
            click_right(config)
            if not sleep_with_control(float(config.get("wait_after_ignore", 1.0)), control):
                print("Stopped after IGNORE.")
                return

        print(f"Max attempts reached: {max_attempts}")

    finally:
        control.unregister_hotkeys()


def list_targets(targets_db):
    targets = targets_db.get("targets", [])

    if not targets:
        print("No targets.")
        return

    print("\n=== Targets ===")
    for i, target in enumerate(targets, start=1):
        mode = target.get("value_mode", "exact")

        if mode == "range":
            value_text = f"{target.get('min_value')}..{target.get('max_value')}"
        else:
            value_text = str(target.get("value"))

        print(
            f"{i}. {target.get('name')} | "
            f"text='{target.get('stat_text')}' | "
            f"value={value_text} ({mode})"
        )


def select_target(targets_db):
    targets = targets_db.get("targets", [])

    if not targets:
        print("No targets available.")
        return None

    list_targets(targets_db)

    try:
        choice = int(input("Select target number: ").strip())
    except ValueError:
        print("Invalid number.")
        return None

    if choice < 1 or choice > len(targets):
        print("Invalid target number.")
        return None

    selected = targets[choice - 1]
    print(f"Selected target: {selected['name']}")
    return selected


def add_target(targets_db):
    print("\n=== Add target ===")

    stat_text = input("Stat text as shown in game: ").strip()

    if not stat_text:
        print("Empty stat text. Cancelled.")
        return

    print("\nValue condition:")
    print("1. exact value")
    print("2. >= value")
    print("3. > value")
    print("4. <= value")
    print("5. < value")
    print("6. from min to max")

    condition = input("Choose condition: ").strip()

    target = {
        "id": f"{safe_filename(stat_text)}_{int(time.time())}",
        "stat_text": stat_text
    }

    if condition == "1":
        target["value_mode"] = "exact"
        target["value"] = float(input("Target value: ").strip())

    elif condition == "2":
        target["value_mode"] = "greater_or_equal"
        target["value"] = float(input("Target value: ").strip())

    elif condition == "3":
        target["value_mode"] = "greater"
        target["value"] = float(input("Target value: ").strip())

    elif condition == "4":
        target["value_mode"] = "less_or_equal"
        target["value"] = float(input("Target value: ").strip())

    elif condition == "5":
        target["value_mode"] = "less"
        target["value"] = float(input("Target value: ").strip())

    elif condition == "6":
        target["value_mode"] = "range"
        target["min_value"] = float(input("Min value: ").strip())
        target["max_value"] = float(input("Max value: ").strip())

    else:
        print("Invalid condition.")
        return

    default_name = f"{stat_text} {target.get('value', '')}".strip()
    name = input(f"Display name [{default_name}]: ").strip()

    if not name:
        name = default_name

    target["name"] = name

    threshold_input = input("Template threshold [0.72]: ").strip()

    if threshold_input:
        target["template_threshold"] = float(threshold_input)

    targets_db["targets"].append(target)
    save_json(TARGETS_PATH, targets_db)

    print(f"Target added: {target['name']}")


def delete_target(targets_db):
    targets = targets_db.get("targets", [])

    if not targets:
        print("No targets to delete.")
        return

    list_targets(targets_db)

    try:
        choice = int(input("Delete target number: ").strip())
    except ValueError:
        print("Invalid number.")
        return

    if choice < 1 or choice > len(targets):
        print("Invalid target number.")
        return

    deleted = targets.pop(choice - 1)
    save_json(TARGETS_PATH, targets_db)

    print(f"Deleted target: {deleted.get('name')}")


def list_templates(templates_db):
    templates = templates_db.get("templates", [])

    print("\n=== Templates ===")

    if not templates:
        print("No templates saved yet.")
        return

    grouped = {}

    for item in templates:
        grouped.setdefault(item["stat_text"], []).append(item)

    for stat_text, items in grouped.items():
        print(f"\n{stat_text}: {len(items)} template(s)")
        for item in items:
            print(f"  - {item['file']}")


def wait_for_mouse_position(message):
    print(message)
    print("Move mouse to the required position and press Enter.")
    input()
    pos = pyautogui.position()
    print(f"Saved position: ({pos.x}, {pos.y})")
    return [pos.x, pos.y]


def wait_for_region(message):
    print(message)

    top_left = wait_for_mouse_position("Set top-left corner.")
    bottom_right = wait_for_mouse_position("Set bottom-right corner.")

    x1, y1 = top_left
    x2, y2 = bottom_right

    x = min(x1, x2)
    y = min(y1, y2)
    w = abs(x2 - x1)
    h = abs(y2 - y1)

    region = [x, y, w, h]

    print(f"Saved region: {region}")
    return region


def calibrate(config):
    print("\n=== Calibration ===")
    print("Keep game window fixed. Do not move it after calibration.")

    config["left_button"] = wait_for_mouse_position(
        "Point mouse to LEFT button: Очистить / Обмен."
    )

    config["right_button"] = wait_for_mouse_position(
        "Point mouse to RIGHT button: Игнор / Вернуть."
    )

    config["ocr_regions"]["stat_name"] = wait_for_region(
        "Select STAT TEXT region. It must contain only text, for example: Физ. Атака."
    )

    config["ocr_regions"]["stat_value"] = wait_for_region(
        "Select VALUE region. It must contain only number, for example: 3000.00."
    )

    save_json(CONFIG_PATH, config)

    print("Calibration saved to config.json.")


def show_config(config):
    print("\n=== Config ===")
    print(json.dumps(config, ensure_ascii=False, indent=4))


def setup_tesseract(config):
    tesseract_path = config.get("tesseract_path")

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    if tesseract_path and not os.path.exists(tesseract_path):
        print(f"Warning: Tesseract not found at: {tesseract_path}")
        print("Check config.json -> tesseract_path")


def main_menu():
    config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    targets_db = load_json(TARGETS_PATH, DEFAULT_TARGETS)
    templates_db = load_json(TEMPLATES_PATH, DEFAULT_TEMPLATES)

    setup_tesseract(config)

    current_target = None

    targets = targets_db.get("targets", [])
    if targets:
        current_target = targets[0]

    while True:
        print("\n=== Roll Bot v5 Template Matching ===")

        if current_target:
            print(f"Current target: {current_target['name']}")
        else:
            print("Current target: None")

        print("1. Start bot")
        print("2. Select target")
        print("3. Add target")
        print("4. Delete target")
        print("5. List targets")
        print("6. Test recognition")
        print("7. Calibrate coordinates and OCR regions")
        print("8. Show config")
        print("9. Exit")
        print("10. Save current stat as template")
        print("11. List templates")

        choice = input("Choose option: ").strip()

        if choice == "1":
            start_bot(config, targets_db, templates_db, current_target)

        elif choice == "2":
            selected = select_target(targets_db)
            if selected:
                current_target = selected

        elif choice == "3":
            add_target(targets_db)
            targets_db = load_json(TARGETS_PATH, DEFAULT_TARGETS)

        elif choice == "4":
            delete_target(targets_db)
            targets_db = load_json(TARGETS_PATH, DEFAULT_TARGETS)
            current_target = targets_db.get("targets", [None])[0]

        elif choice == "5":
            list_targets(targets_db)

        elif choice == "6":
            test_recognition(config, targets_db, templates_db, current_target)

        elif choice == "7":
            calibrate(config)
            config = load_json(CONFIG_PATH, DEFAULT_CONFIG)

        elif choice == "8":
            show_config(config)

        elif choice == "9":
            print("Exit.")
            break

        elif choice == "10":
            save_current_stat_template(config, templates_db)
            templates_db = load_json(TEMPLATES_PATH, DEFAULT_TEMPLATES)

        elif choice == "11":
            list_templates(templates_db)

        else:
            print("Unknown option.")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")