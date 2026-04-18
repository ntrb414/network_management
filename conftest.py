from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


_RUN_STATE: dict[str, object] = {
    "log_path": None,
    "failed_cases": [],
    "failed_details": [],
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_header(log_path: Path) -> None:
    if log_path.exists() and log_path.stat().st_size > 0:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write("# Test Process Log\n\n")
        f.write("| Datetime | Action | Result |\n")
        f.write("| --- | --- | --- |\n")


def _append_log(action: str, result: str) -> None:
    log_path = _RUN_STATE.get("log_path")
    if not isinstance(log_path, Path):
        return
    safe_result = result.replace("\n", " ").replace("|", "\\|")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"| {_now()} | {action} | {safe_result} |\n")


def _failure_reason(report) -> str:
    longrepr = getattr(report, "longrepr", None)
    if longrepr is not None:
        reprcrash = getattr(longrepr, "reprcrash", None)
        if reprcrash is not None:
            path = getattr(reprcrash, "path", "")
            lineno = getattr(reprcrash, "lineno", None)
            message = getattr(reprcrash, "message", "")
            location = path
            if path and lineno is not None:
                location = f"{path}:{lineno}"
            reason = f"{location} {message}".strip()
            if reason:
                return reason[:280] + ("..." if len(reason) > 280 else "")

    text = getattr(report, "longreprtext", "")
    if not text:
        text = str(longrepr) if longrepr is not None else "unknown"

    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.startswith(("=", "_", "-", ">")):
            continue
        return line[:280] + ("..." if len(line) > 280 else "")

    return "unknown"


def pytest_addoption(parser):
    parser.addoption(
        "--test-log-file",
        action="store",
        default=os.environ.get("TEST_PROCESS_LOG_FILE", "test_process_log.md"),
        help="Markdown file path for test process logs.",
    )


def pytest_sessionstart(session):
    configured_path = session.config.getoption("--test-log-file")
    log_path = Path(configured_path)
    if not log_path.is_absolute():
        log_path = Path(session.config.rootpath) / log_path

    _RUN_STATE["log_path"] = log_path
    _RUN_STATE["failed_cases"] = []
    _RUN_STATE["failed_details"] = []

    _ensure_header(log_path)
    command = " ".join(sys.argv)
    _append_log(
        "start",
        f"FLAG=INFO; command={command}; cwd={session.config.rootpath}; mode=append",
    )


def pytest_collection_finish(session):
    _append_log("collect", f"FLAG=INFO; collected={len(session.items)}")


def pytest_runtest_logreport(report):
    failed_cases = _RUN_STATE.get("failed_cases")

    if report.when == "call":
        if report.passed:
            _append_log("test_case", f"FLAG=PASS; nodeid={report.nodeid}")
            return
        if report.failed:
            reason = _failure_reason(report)
            _append_log(
                "test_case",
                f"FLAG=NOT PASS; nodeid={report.nodeid}; reason={reason}",
            )
            if isinstance(failed_cases, list):
                failed_cases.append(report.nodeid)
            failed_details = _RUN_STATE.get("failed_details")
            if isinstance(failed_details, list):
                failed_details.append(f"{report.nodeid} => {reason}")
            return
        if report.skipped:
            _append_log("test_case", f"FLAG=NOT PASS; nodeid={report.nodeid}; reason=skipped")
            return

    if report.when in ("setup", "teardown") and report.failed:
        case_id = f"{report.nodeid}; phase={report.when}"
        reason = _failure_reason(report)
        _append_log(
            "test_case",
            f"FLAG=NOT PASS; nodeid={case_id}; reason={reason}",
        )
        if isinstance(failed_cases, list):
            failed_cases.append(case_id)
        failed_details = _RUN_STATE.get("failed_details")
        if isinstance(failed_details, list):
            failed_details.append(f"{case_id} => {reason}")
        return

    if report.when == "setup" and report.skipped:
        _append_log("test_case", f"FLAG=NOT PASS; nodeid={report.nodeid}; phase=setup; reason=skipped")


def pytest_sessionfinish(session, exitstatus):
    terminal_reporter = session.config.pluginmanager.getplugin("terminalreporter")
    stats = terminal_reporter.stats if terminal_reporter else {}

    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    skipped = len(stats.get("skipped", []))
    errors = len(stats.get("error", []))
    xfailed = len(stats.get("xfailed", []))
    xpassed = len(stats.get("xpassed", []))

    summary = (
        f"exitstatus={exitstatus}; passed={passed}; failed={failed}; "
        f"skipped={skipped}; errors={errors}; xfailed={xfailed}; xpassed={xpassed}"
    )
    run_flag = "PASS" if exitstatus == 0 and failed == 0 and errors == 0 else "NOT PASS"
    _append_log("finish", f"FLAG={run_flag}; {summary}")

    failed_cases = _RUN_STATE.get("failed_cases")
    if isinstance(failed_cases, list) and failed_cases:
        failed_details = _RUN_STATE.get("failed_details")
        if isinstance(failed_details, list) and failed_details:
            _append_log("failed_cases", f"FLAG=NOT PASS; {'; '.join(failed_details)}")
        else:
            _append_log("failed_cases", f"FLAG=NOT PASS; {', '.join(failed_cases)}")
