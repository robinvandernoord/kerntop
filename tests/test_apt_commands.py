import asyncio

import pytest

from kerntop.apt_commands import (
    PreviewAction,
    QueuedAction,
    apply_command,
    preview_command,
    run_preview,
    stream_command,
    transaction_command,
)
from kerntop.kernels import KernelRecord


def record(name: str, installed: bool, running: bool = False) -> KernelRecord:
    version = "1.0" if installed else None
    candidate = "1.0"
    return KernelRecord(name, installed, version, candidate, running, ())


def test_apply_command_builds_install_and_remove_commands() -> None:
    assert apply_command(
        PreviewAction.INSTALL, record("linux-image-6.12", installed=False)
    ) == ("apt-get", "--assume-yes", "install", "linux-image-6.12")
    assert apply_command(
        PreviewAction.REMOVE, record("linux-image-6.11", installed=True)
    ) == ("apt-get", "--assume-yes", "remove", "linux-image-6.11")


@pytest.mark.parametrize(
    ("action", "kernel", "message"),
    (
        (
            PreviewAction.INSTALL,
            record("linux-image-6.12", installed=True),
            "already installed",
        ),
        (
            PreviewAction.REMOVE,
            record("linux-image-6.12", installed=False),
            "Only installed kernels",
        ),
        (
            PreviewAction.REMOVE,
            record("linux-image-6.12", installed=True, running=True),
            "currently running",
        ),
    ),
)
def test_apply_command_rejects_unsafe_actions(
    action: PreviewAction, kernel: KernelRecord, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        apply_command(action, kernel)


def test_transaction_command_builds_one_simulated_transaction() -> None:
    actions = (
        QueuedAction(
            PreviewAction.INSTALL,
            record("linux-image-6.12", installed=False),
        ),
        QueuedAction(
            PreviewAction.REMOVE,
            record("linux-image-6.11", installed=True),
        ),
    )

    assert transaction_command(actions) == (
        "apt-get",
        "--simulate",
        "install",
        "linux-image-6.12",
        "linux-image-6.11-",
    )
    assert transaction_command(actions, simulate=False)[1] == "--assume-yes"


@pytest.mark.parametrize(
    ("actions", "message"),
    (
        ((), "no queued"),
        (
            (
                QueuedAction(
                    PreviewAction.INSTALL,
                    record("linux-image-6.12", installed=False),
                ),
                QueuedAction(
                    PreviewAction.REMOVE,
                    record("linux-image-6.12", installed=True),
                ),
            ),
            "once",
        ),
        (
            (
                QueuedAction(
                    PreviewAction.REMOVE,
                    record("linux-image-6.12", installed=True, running=True),
                ),
            ),
            "currently running",
        ),
        (
            (
                QueuedAction(
                    PreviewAction.REMOVE,
                    record("linux-image-6.12", installed=False),
                ),
            ),
            "Only installed kernels",
        ),
        (
            (
                QueuedAction(
                    PreviewAction.INSTALL,
                    record("linux-image-6.12", installed=True),
                ),
            ),
            "cannot be queued",
        ),
    ),
)
def test_transaction_command_rejects_invalid_queues(
    actions: tuple[QueuedAction, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        transaction_command(actions)


def test_run_preview_returns_real_apt_simulation_result() -> None:
    result = run_preview(
        PreviewAction.INSTALL,
        record("linux-image-6.12", installed=False),
    )

    assert result.command == (
        "apt-get",
        "--simulate",
        "install",
        "linux-image-6.12",
    )
    assert isinstance(result.return_code, int)
    assert isinstance(result.output, str)
    assert "simulation" in result.output.lower()


def test_stream_command_writes_decoded_lines_and_returns_exit_code() -> None:
    lines: list[str] = []
    exit_code = asyncio.run(
        stream_command(("printf", "first\nbad-\\377\nlast"), lines.append)
    )

    assert lines == ["first", "bad-�", "last"]
    assert exit_code == 0
