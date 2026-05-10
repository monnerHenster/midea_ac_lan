"""Connection and command coordination for Midea devices."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from midealocal.device import MideaDevice
from midealocal.exceptions import SocketException

CONNECTION_MANAGERS = "connection_managers"

_LOGGER = logging.getLogger(__name__)

_ResultT = TypeVar("_ResultT")
_RECOVERABLE_EXCEPTIONS = (
    BrokenPipeError,
    ConnectionAbortedError,
    ConnectionResetError,
    OSError,
    TimeoutError,
    SocketException,
)


class MideaConnectionManager:
    """Serialize socket access and recover once from broken command pipes."""

    def __init__(self, device: MideaDevice) -> None:
        """Initialize the connection manager."""
        self._device = device
        self._lock = threading.RLock()
        self._state = "created"
        self._last_error: str | None = None
        self._last_error_at: float | None = None
        self._last_success_at: float | None = None
        self._last_reconnect_at: float | None = None
        self._reconnect_count = 0
        self._command_failures = 0
        self._original_connect = device.connect
        self._original_close_socket = device.close_socket
        self._original_refresh_status = device.refresh_status
        self._original_build_send = device.build_send
        self._original_send_heartbeat = device.send_heartbeat
        self._original_send_command = device.send_command

    @property
    def diagnostic_data(self) -> dict[str, Any]:
        """Return runtime connection diagnostics."""
        return {
            "state": self._state,
            "last_error": self._last_error,
            "last_error_at": self._last_error_at,
            "last_success_at": self._last_success_at,
            "last_reconnect_at": self._last_reconnect_at,
            "reconnect_count": self._reconnect_count,
            "command_failures": self._command_failures,
        }

    def connect(self, check_protocol: bool = False) -> bool:
        """Connect with serialized socket access."""
        with self._lock:
            self._state = "connecting"
            connected = self._original_connect(check_protocol=check_protocol)
            if connected:
                self._record_success("connected")
            else:
                self._record_error("connect", RuntimeError("connect returned false"))
            return connected

    def close_socket(self) -> None:
        """Close socket with serialized socket access."""
        with self._lock:
            self._state = "closing"
            self._original_close_socket()
            self._state = "disconnected"

    def refresh_status(self, check_protocol: bool = False) -> None:
        """Refresh status with serialized socket writes."""
        with self._lock:
            try:
                self._original_refresh_status(check_protocol=check_protocol)
                self._record_success("ready")
            except _RECOVERABLE_EXCEPTIONS as err:
                self._record_error("refresh_status", err)
                raise

    def build_send(self, cmd: Any, query: bool = False) -> None:  # noqa: ANN401
        """Serialize message sends from commands, refresh, and heartbeat."""
        with self._lock:
            try:
                self._original_build_send(cmd, query=query)
                self._record_success("ready")
            except _RECOVERABLE_EXCEPTIONS as err:
                self._record_error("build_send", err)
                raise

    def send_heartbeat(self) -> None:
        """Send heartbeat with serialized socket writes."""
        with self._lock:
            try:
                self._original_send_heartbeat()
                self._record_success("ready")
            except _RECOVERABLE_EXCEPTIONS as err:
                self._record_error("heartbeat", err)
                raise

    def send_command(self, cmd_type: Any, cmd_body: bytearray) -> None:  # noqa: ANN401
        """Send a raw command through the managed command path."""
        self.run_command(
            "send_command",
            lambda: self._original_send_command(cmd_type, cmd_body),
        )

    def run_command(
        self,
        description: str,
        action: Callable[[], _ResultT],
    ) -> _ResultT:
        """Run a device command, reconnecting once if the TCP socket broke."""
        try:
            with self._lock:
                result = action()
                self._record_success("ready")
                return result
        except _RECOVERABLE_EXCEPTIONS as err:
            return self._retry_after_reconnect(description, action, err)

    def _retry_after_reconnect(
        self,
        description: str,
        action: Callable[[], _ResultT],
        err: BaseException,
    ) -> _ResultT:
        with self._lock:
            self._record_error(description, err)
            _LOGGER.warning(
                "Midea command %s failed for device %s (%s), reconnecting once",
                description,
                self._device.device_id,
                err,
            )
            self._original_close_socket()
            self._device.set_available(False)
            self._state = "reconnecting"
            if not self._original_connect(check_protocol=True):
                self._record_error(description, RuntimeError("reconnect returned false"))
                raise err
            self._reconnect_count += 1
            self._last_reconnect_at = time.time()
            try:
                result = action()
            except _RECOVERABLE_EXCEPTIONS as retry_err:
                self._record_error(f"{description} retry", retry_err)
                self._original_close_socket()
                self._device.set_available(False)
                raise
            self._record_success("ready")
            return result

    def _record_success(self, state: str) -> None:
        self._state = state
        self._last_success_at = time.time()

    def _record_error(self, operation: str, err: BaseException) -> None:
        self._state = "error"
        self._command_failures += 1
        self._last_error = f"{operation}: {type(err).__name__}: {err}"
        self._last_error_at = time.time()


def install_device_connection_manager(device: MideaDevice) -> MideaConnectionManager:
    """Install a connection manager on a MideaDevice instance."""
    existing = device.__dict__.get("_midea_connection_manager")
    if isinstance(existing, MideaConnectionManager):
        return existing

    manager = MideaConnectionManager(device)
    device.__dict__["_midea_connection_manager"] = manager
    device.connect = manager.connect  # type: ignore[method-assign]
    device.close_socket = manager.close_socket  # type: ignore[method-assign]
    device.refresh_status = manager.refresh_status  # type: ignore[method-assign]
    device.build_send = manager.build_send  # type: ignore[method-assign]
    device.send_heartbeat = manager.send_heartbeat  # type: ignore[method-assign]
    device.send_command = manager.send_command  # type: ignore[method-assign]
    return manager


def get_connection_manager(device: MideaDevice) -> MideaConnectionManager | None:
    """Return the installed connection manager for a device."""
    manager = device.__dict__.get("_midea_connection_manager")
    if isinstance(manager, MideaConnectionManager):
        return manager
    return None


def run_device_command(
    device: MideaDevice,
    description: str,
    action: Callable[[], _ResultT],
) -> _ResultT:
    """Run a device command through the connection manager when available."""
    manager = get_connection_manager(device)
    if manager is None:
        return action()
    return manager.run_command(description, action)
