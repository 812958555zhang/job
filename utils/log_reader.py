"""
日志文件读取工具 - 供 GUI 实时日志面板使用
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from utils.logger import DEFAULT_LOG_DIR, DEFAULT_LOG_FILE

MAX_DISPLAY_LINES = 500

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_LEVEL_PATTERN = re.compile(r"\|\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|")


def get_log_file_path() -> Path:
    return DEFAULT_LOG_FILE


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _detect_level(line: str) -> Optional[str]:
    match = _LEVEL_PATTERN.search(line)
    return match.group(1) if match else None


def _read_tail_lines(path: Path, max_lines: int = MAX_DISPLAY_LINES) -> List[str]:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if size == 0:
                return []

            block_size = 8192
            buffer = b""
            position = size

            while position > 0 and buffer.count(b"\n") <= max_lines + 1:
                read_len = min(block_size, position)
                position -= read_len
                handle.seek(position)
                buffer = handle.read(read_len) + buffer

            text = buffer.decode("utf-8", errors="replace")
            lines = text.splitlines()
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
            return lines
    except OSError:
        return []


def read_log_tail(
    level_filter: str = "ALL",
    max_lines: int = MAX_DISPLAY_LINES,
    log_path: Optional[Path] = None,
) -> Tuple[str, str, str]:
    path = log_path or get_log_file_path()
    timestamp = datetime.now().strftime("%H:%M:%S")

    if not path.exists():
        return (
            "=== BOSS直聘求职助手日志 ===\n日志文件尚未生成，等待系统写入...\n",
            "总行数: 0 | INFO: 0 | WARNING: 0 | ERROR: 0",
            timestamp,
        )

    raw_lines = _read_tail_lines(path, max_lines=max_lines * 3)
    if not raw_lines:
        raw = _read_file_text(path)
        if raw.startswith("=== 读取失败"):
            return raw, "总行数: 0 | INFO: 0 | WARNING: 0 | ERROR: 0", timestamp
        raw_lines = raw.splitlines()

    lines = [strip_ansi(line) for line in raw_lines if line.strip()]

    info_count = warning_count = error_count = 0
    for line in lines:
        level = _detect_level(line)
        if level == "INFO":
            info_count += 1
        elif level == "WARNING":
            warning_count += 1
        elif level in ("ERROR", "CRITICAL"):
            error_count += 1

    total = len(lines)
    stats = (
        f"总行数: {total} | INFO: {info_count} | "
        f"WARNING: {warning_count} | ERROR: {error_count}"
    )

    if level_filter and level_filter != "ALL":
        level_filter = level_filter.upper()
        filtered = []
        for line in lines:
            level = _detect_level(line)
            if level == level_filter:
                filtered.append(line)
            elif level_filter == "ERROR" and level == "CRITICAL":
                filtered.append(line)
        lines = filtered

    if not lines:
        return f"（无符合级别 {level_filter} 的日志）\n", stats, timestamp

    truncated = len(lines) > max_lines
    display_lines = lines[-max_lines:]
    text = "\n".join(display_lines)
    if truncated:
        text = f"... 仅显示最近 {max_lines} 行（共 {len(lines)} 行匹配） ...\n" + text

    return text, stats, timestamp


def clear_log_file(log_path: Optional[Path] = None) -> bool:
    path = log_path or get_log_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.truncate(0)
        return True
    except OSError:
        return False


def export_log_file(log_path: Optional[Path] = None) -> Optional[str]:
    path = log_path or get_log_file_path()
    if not path.exists() or path.stat().st_size == 0:
        return None

    export_name = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    export_path = DEFAULT_LOG_DIR / export_name
    export_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, export_path)
    return str(export_path.resolve())


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gbk")
        except Exception as exc:
            return f"=== 读取失败: {exc} ===\n"
    except OSError as exc:
        return f"=== 读取失败: {exc} ===\n"
