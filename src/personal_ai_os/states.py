from __future__ import annotations


TASK_STATES = (
    "QUEUED",
    "IN_PROGRESS",
    "REVIEW",
    "DONE",
    "BLOCKED",
    "PAUSED",
    "ARCHIVED",
)

TERMINAL_STATES = {"DONE", "ARCHIVED"}
OVERLAY_STATES = {"BLOCKED", "PAUSED"}

TASK_STATE_LABELS = {
    "QUEUED": "待分配",
    "IN_PROGRESS": "进行中",
    "REVIEW": "待验收",
    "DONE": "已收口",
    "BLOCKED": "已阻塞",
    "PAUSED": "已暂停",
    "ARCHIVED": "已归档",
}
