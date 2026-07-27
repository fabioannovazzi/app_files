from modules.utilities.ui_notifier import Notifier, NullNotifier


def display_performance_metrics(data: dict, notifier: Notifier | None = None) -> None:
    """Record timing and memory metrics via the notifier."""
    if not data:
        return
    notify = notifier or NullNotifier()
    step = data.get("step", "")
    description = data.get("description", "")
    if "memory_percent" in data and data["memory_percent"] > 50:
        notify.info(
            f"Memory usage {step} ({description}): {data['memory_percent']:.0f}%",
            metric="memory_percent",
        )
    if "time_delta" in data and data["time_delta"] > 0.1:
        notify.info(
            f"Step {step} ({description}): {data['time_delta']:.2f} seconds",
            metric="time_delta",
        )
    if "total_time" in data:
        notify.info(
            f"Total: {data['total_time']:.2f} seconds",
            metric="total_time",
        )
