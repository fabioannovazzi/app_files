import modules.layout.performance as perf


class DummyNotifier:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def info(self, message: str, **_context: object) -> None:
        self.calls.append(message)


def test_display_performance_metrics_writes_all_when_over_thresholds():
    # Arrange
    notifier = DummyNotifier()
    data = {
        "step": "Load",
        "description": "Reading data",
        "memory_percent": 72.4,  # > 50 triggers memory line
        "time_delta": 1.237,  # > 0.1 triggers time line
        "total_time": 4.5,
    }

    # Act
    perf.display_performance_metrics(data, notifier=notifier)

    # Assert
    assert notifier.calls == [
        "Memory usage Load (Reading data): 72%",
        "Step Load (Reading data): 1.24 seconds",
        "Total: 4.50 seconds",
    ]


def test_display_performance_metrics_thresholds_exclude_memory_and_time_but_total_prints():
    # Arrange: boundary values should not print memory/time; only total should appear
    notifier = DummyNotifier()
    data = {
        "step": "S",
        "description": "D",
        "memory_percent": 50.0,  # not > 50
        "time_delta": 0.10,  # not > 0.1
        "total_time": 3.333,
    }

    # Act
    perf.display_performance_metrics(data, notifier=notifier)

    # Assert
    assert notifier.calls == ["Total: 3.33 seconds"]


def test_display_performance_metrics_no_output_when_empty_or_below_thresholds():
    # Arrange: below thresholds and no total -> no writes
    notifier = DummyNotifier()
    data = {
        "step": "X",
        "description": "Y",
        "memory_percent": 10.0,
        "time_delta": 0.05,
    }

    # Act
    perf.display_performance_metrics(data, notifier=notifier)

    # Assert
    assert notifier.calls == []
