#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 7 Boost Toolkit
========================
Реальная программа для чистки и диагностики Windows 7.
Не меняет стиль системы, только освобождает место и наводит порядок.

УСТАНОВКА:
1. Python 3.8.10 (обязательно скачать с python.org и поставить галочку "Add Python to PATH")
2. В командной строке: pip install "psutil<6.0"
3. Запустить скрипт от имени администратора (правый клик -> Запуск от имени администратора)
"""

import os
import sys
import ctypes
import shutil
import hashlib
import subprocess
import winreg
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    import psutil
except ImportError:
    print("ОШИБКА: Библиотека psutil не установлена.")
    print("Откройте командную строку и введите: pip install \"psutil<6.0\"")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

LOG = Path(__file__).with_name("boost_log.txt")

def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def relaunch_as_admin():
    if is_admin():
        return
    print("Требуются права администратора. Перезапуск...")
    params = " ".join(f'"{a}"' for a in sys.argv)
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    except Exception:
        pass
    sys.exit(0)

def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def clean_temp():
    folders = {
        Path(os.environ.get("TEMP", "")),
        Path(os.environ.get("TMP", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
        Path("C:/Windows/Temp"),
    }
    freed, skipped = 0, 0
    for folder in folders:
        if not folder or not str(folder) or not folder.exists():
            continue
        print(f"  Очистка: {folder}")
        for item in folder.rglob("*"):
            try:
                if item.is_file():
                    freed += item.stat().st_size
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except (PermissionError, OSError):
                skipped += 1
    log(f"Temp очищен: {human(freed)} (пропущено занятых: {skipped})")

def empty_bin():
    try:
        r = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
        log("Корзина очищена" if r == 0 else f"Корзина: код {r}")
    except Exception as e:
        log(f"Корзина: ошибка {e}")

def flush_dns():
    try:
        subprocess.run(["ipconfig", "/flushdns"], check=True, capture_output=True)
        log("DNS-кеш сброшен")
    except Exception as e:
        log(f"DNS: ошибка {e}")

def clean_prefetch(days=30):
    pf = Path("C:/Windows/Prefetch")
    if not pf.exists():
        log("Папка Prefetch не найдена")
        return
    cutoff = datetime.now().timestamp() - days * 86400
    n = 0
    for f in pf.glob("*.pf"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            pass
    log(f"Prefetch: удалено {n} старых файлов")

def top_processes(n=10):
    log(f"--- Топ-{n} процессов по RAM ---")
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["memory_info"].rss, p.info["name"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(reverse=True)
    for size, name in procs[:n]:
        log(f"  {human(size):>10}  {name}")

def find_dupes_downloads():
    d = Path(os.path.expandvars(r"%USERPROFILE%\Downloads"))
    if not d.exists():
        log("Папка Downloads не найдена")
        return
    hashes = defaultdict(list)
    for f in d.rglob("*"):
        if f.is_file():
            try:
                hashes[hashlib.md5(f.read_bytes()).hexdigest()].append(f)
            except OSError:
                pass
    dupes = {h: v for h, v in hashes.items() if len(v) > 1}
    log(f"--- Дубликаты в Downloads: {len(dupes)} групп ---")
    for _, files in dupes.items():
        for f in files:
            try:
                log(f"  {human(f.stat().st_size):>10}  {f}")
            except OSError:
                pass

def backup_startup():
    out = LOG.with_name(f"startup_backup_{datetime.now():%Y%m%d_%H%M%S}.txt")
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]
    with out.open("w", encoding="utf-8") as fh:
        for hive, path in keys:
            try:
                with winreg.OpenKey(hive, path) as k:
                    fh.write(f"\n[{path}]\n")
                    i = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(k, i)
                            i += 1
                            fh.write(f"{name} = {val}\n")
                        except OSError:
                            break
            except FileNotFoundError:
                pass
    log(f"Автозагрузка сохранена в {out.name}")

def run_cleanmgr():
    log("Запуск cleanmgr (Очистка диска)...")
    try:
        subprocess.Popen(["cleanmgr", "/sagerun:1"])
    except Exception as e:
        log(f"cleanmgr: {e}")

def run_defrag():
    log("Запуск дефрагментации C: (только для HDD)...")
    try:
        subprocess.Popen(["defrag", "C:", "/O", "/U"])
    except Exception as e:
        log(f"defrag: {e}")

def menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 45)
    print("      WINDOWS 7 BOOST TOOLKIT")
    print("=" * 45)
    print("1. Полная чистка (temp + корзина + DNS + prefetch)")
    print("2. Только временные файлы (temp)")
    print("3. Только корзина")
    print("4. Сброс DNS-кеша")
    print("5. Топ-10 процессов по RAM")
    print("6. Дубликаты в Downloads")
    print("7. Бэкап автозагрузки")
    print("8. Запустить встроенную Очистку диска (cleanmgr)")
    print("9. Дефрагментация C: (ТОЛЬКО HDD!)")
    print("0. Выход")
    print("=" * 45)
    return input("Выберите пункт: ").strip()

def main():
    relaunch_as_admin()
    log("=== Программа запущена ===")
    while True:
        c = menu()
        if c == "0":
            break
        elif c == "1":
            clean_temp(); empty_bin(); flush_dns(); clean_prefetch()
            input("\nГотово. Нажмите Enter...")
        elif c == "2":
            clean_temp()
            input("\nГотово. Нажмите Enter...")
        elif c == "3":
            empty_bin()
            input("\nГотово. Нажмите Enter...")
        elif c == "4":
            flush_dns()
            input("\nГотово. Нажмите Enter...")
        elif c == "5":
            top_processes()
            input("\nГотово. Нажмите Enter...")
        elif c == "6":
            find_dupes_downloads()
            input("\nГотово. Нажмите Enter...")
        elif c == "7":
            backup_startup()
            input("\nГотово. Нажмите Enter...")
        elif c == "8":
            run_cleanmgr()
            input("\nГотово. Нажмите Enter...")
        elif c == "9":
            run_defrag()
            input("\nГотово. Нажмите Enter...")
    log("=== Программа завершена ===")

if __name__ == "__main__":
    main()
