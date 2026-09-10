# -*- coding: utf-8 -*-
"""
统一 DB 任务通道封装

提供三个优先级通道：
  - critical_channel：同步阻塞，主流程必须等待
  - async_channel：异步线程执行，不阻塞当前请求
  - background_channel：内存队列 + 后台 worker，适合低优先级写操作

所有 async/background 任务自动捕获错误、打印 error log 和耗时日志，
失败不影响用户当前响应。

usage:
    from .services.db_channel import enqueue_db_task, DbChannel, reset_channel_metrics, get_channel_metrics

    # critical
    profile = enqueue_db_task(DbChannel.CRITICAL, "load_profile", handler, app=app, user_id=uid)

    # async
    enqueue_db_task(DbChannel.ASYNC, "save_message", handler, app=app, msg="...")

    # background
    enqueue_db_task(DbChannel.BACKGROUND, "update_profile", handler, app=app, profile_id=pid)

background_channel 当前使用内存 Queue，保留接口，后续可替换为 Redis / Celery / BullMQ。
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from queue import Queue
from typing import Any, Callable

logger = logging.getLogger(__name__)


class DbChannel(Enum):
    """DB 操作通道枚举"""
    CRITICAL = "critical"
    ASYNC = "async"
    BACKGROUND = "background"


# ── 线程池 ──────────────────────────────────────────────
_async_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="db_async")

# ── 内存队列（background 通道） ─────────────────────────┐
# 保留 enqueue / process / shutdown 接口，后续可替换为：   │
# - Redis / BullMQ / Celery                               │
# - 替换时只需修改 _background_queue 的 put/get 逻辑       │
# ─────────────────────────────────────────────────────────┘
_background_queue: Queue = Queue()

# ── 请求级 metrics（每次请求前 reset） ──────────────────
_channel_metrics: dict[str, Any] = {
    "dbCriticalMs": 0.0,
    "dbAsyncQueuedMs": 0.0,
    "dbBackgroundQueuedMs": 0.0,
    "dbAsyncTaskCount": 0,
    "dbBackgroundTaskCount": 0,
    "dbChannelErrors": 0,
}

# ── background worker ───────────────────────────────────
_background_worker_running = True


def _background_worker_loop():
    """后台队列 worker：从 _background_queue 取任务执行"""
    while _background_worker_running:
        task = _background_queue.get()
        if task is None:  # 哨兵值，通知退出
            break
        try:
            t0 = time.time()
            handler = task["handler"]
            payload = task["payload"]
            app = task.get("app")
            if app is not None:
                with app.app_context():
                    handler(**payload)
            else:
                handler(**payload)
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            logger.info("[db_channel] background task '%s' OK in %.1fms", task["task_name"], elapsed_ms)
        except Exception as exc:
            _channel_metrics["dbChannelErrors"] += 1
            logger.error("[db_channel] background task '%s' FAILED: %s\n%s",
                         task["task_name"], exc, traceback.format_exc())
        finally:
            _background_queue.task_done()


_bg_worker = threading.Thread(target=_background_worker_loop, daemon=True, name="db_bg")
_bg_worker.start()


# ── 统一入口 ─────────────────────────────────────────────

def enqueue_db_task(
    channel: DbChannel,
    task_name: str,
    handler: Callable,
    app: Any = None,
    **payload: Any,
) -> Any:
    """统一 DB 任务入口。

    Args:
        channel: DbChannel.CRITICAL / ASYNC / BACKGROUND
        task_name: 描述性名称（用于日志）
        handler: 实际执行 DB 操作的可调用对象
        app: Flask app 实例（async/background 需要 app_context）
        payload: 传给 handler 的关键字参数

    Returns:
        CRITICAL: handler 的返回值
        ASYNC / BACKGROUND: None（即发即忘）
    """
    if channel == DbChannel.CRITICAL:
        t0 = time.time()
        try:
            result = handler(**payload)
            _channel_metrics["dbCriticalMs"] += round((time.time() - t0) * 1000, 1)
            return result
        except Exception as exc:
            _channel_metrics["dbChannelErrors"] += 1
            logger.error("[db_channel] CRITICAL task '%s' FAILED: %s\n%s",
                         task_name, exc, traceback.format_exc())
            raise  # critical 错误必须向上传播

    elif channel == DbChannel.ASYNC:
        t0 = time.time()
        _channel_metrics["dbAsyncTaskCount"] += 1
        try:
            _async_executor.submit(_run_async_task, task_name, handler, payload, app)
        except Exception as exc:
            _channel_metrics["dbChannelErrors"] += 1
            logger.error("[db_channel] failed to queue ASYNC task '%s': %s", task_name, exc)
        _channel_metrics["dbAsyncQueuedMs"] += round((time.time() - t0) * 1000, 1)
        return None

    elif channel == DbChannel.BACKGROUND:
        t0 = time.time()
        _channel_metrics["dbBackgroundTaskCount"] += 1
        try:
            _background_queue.put({
                "task_name": task_name,
                "handler": handler,
                "payload": payload,
                "app": app,
            })
        except Exception as exc:
            _channel_metrics["dbChannelErrors"] += 1
            logger.error("[db_channel] failed to queue BACKGROUND task '%s': %s", task_name, exc)
        _channel_metrics["dbBackgroundQueuedMs"] += round((time.time() - t0) * 1000, 1)
        return None

    else:
        raise ValueError(f"未知 DB 通道: {channel}")


def _run_async_task(task_name: str, handler: Callable, payload: dict, app: Any = None):
    """执行异步任务（在 _async_executor 线程中运行）"""
    try:
        t0 = time.time()
        if app is not None:
            with app.app_context():
                handler(**payload)
        else:
            handler(**payload)
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        logger.info("[db_channel] ASYNC task '%s' OK in %.1fms", task_name, elapsed_ms)
    except Exception as exc:
        _channel_metrics["dbChannelErrors"] += 1
        logger.error("[db_channel] ASYNC task '%s' FAILED: %s\n%s",
                     task_name, exc, traceback.format_exc())


# ── metrics 管理 ────────────────────────────────────────

def reset_channel_metrics():
    """每次请求开始前调用，清空 metrics"""
    for key in _channel_metrics:
        _channel_metrics[key] = 0.0 if isinstance(_channel_metrics[key], float) else 0


def get_channel_metrics() -> dict[str, Any]:
    """返回当前请求的通道 metrics 快照"""
    return dict(_channel_metrics)


# ── 优雅关闭 ────────────────────────────────────────────

def shutdown():
    """停止 background worker（应用关闭时调用）"""
    global _background_worker_running
    _background_worker_running = False
    _background_queue.put(None)
    _async_executor.shutdown(wait=False)