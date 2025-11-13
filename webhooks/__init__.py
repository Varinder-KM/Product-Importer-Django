from typing import Any, Callable


def _get_task(name: str) -> Callable[..., Any]:
    from . import tasks

    return getattr(tasks, name)


def queue_event(*args: Any, **kwargs: Any) -> Any:
    return _get_task("queue_event")(*args, **kwargs)


def queue_webhook(*args: Any, **kwargs: Any) -> Any:
    return _get_task("queue_webhook")(*args, **kwargs)


__all__ = ["queue_event", "queue_webhook"]
