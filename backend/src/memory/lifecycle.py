"""Ephemeral memory lifecycle management for Foresight backend.

Provides the `ephemeral_processing` context manager and decorator to wrap
upload-handling and data-processing routines.
Ensures intermediate DataFrames, byte buffers, raw byte arrays, and parsed
objects are explicitly dereferenced (set to None) and `gc.collect()` is invoked
on exit — including on exception, via a strict try/finally block.
"""

from collections.abc import Callable
from functools import wraps
import gc
import inspect
import io
import sys
from typing import Any, List, Optional, Set

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False


def _is_intermediate_data(val: Any) -> bool:
    """Check if an object represents an intermediate data structure to be dereferenced."""
    if val is None:
        return False

    # Check for pandas DataFrame or Series
    if _PANDAS_AVAILABLE:
        if isinstance(val, (pd.DataFrame, pd.Series)):
            return True

    # Check for byte buffers or IO streams
    if isinstance(val, (io.BytesIO, io.StringIO, io.BufferedIOBase, io.RawIOBase)):
        return True

    # Check for raw bytearrays or byte buffers
    if isinstance(val, bytearray):
        return True
    if isinstance(val, bytes) and len(val) > 1024:
        return True

    # Check for document parser objects (pypdf, docx)
    type_str = str(type(val))
    if any(lib in type_str for lib in ("PdfReader", "docx.document", "docx.parts")):
        return True

    return False


class EphemeralScope:
    """Tracking scope for explicit intermediate object lifecycle management."""

    def __init__(self) -> None:
        self._tracked: List[Any] = []

    def track(self, obj: Any) -> Any:
        """Register an object to be explicitly dereferenced and closed on exit.

        Returns the object for convenient inline assignment:
            df = scope.track(parse_tabular(file_bytes, ext))
        """
        self._tracked.append(obj)
        return obj

    def manage(self, **kwargs: Any) -> None:
        """Register multiple named objects for cleanup."""
        for val in kwargs.values():
            self._tracked.append(val)

    def register(self, *args: Any) -> None:
        """Register one or more objects for cleanup."""
        self._tracked.extend(args)

    def clear(self) -> None:
        """Explicitly close and dereference all registered objects."""
        for obj in self._tracked:
            if hasattr(obj, "close") and callable(obj.close):
                try:
                    obj.close()
                except Exception:
                    pass
            if isinstance(obj, bytearray):
                try:
                    obj.clear()
                except Exception:
                    pass
        # Explicitly dereference tracked list
        self._tracked.clear()


class ephemeral_processing:
    """Context manager and decorator for ephemeral memory lifecycle management.

    Wraps upload-handling and data processing logic, ensuring all intermediate
    DataFrames, byte buffers, and parsed objects are explicitly dereferenced
    (set to None) and `gc.collect()` is called on exit — including on exception,
    via try/finally.

    Usages:
        # 1. Standard context manager:
        with ephemeral_processing():
            df = parse_tabular(file_bytes, ext)
            ...

        # 2. Context manager with explicit tracker scope:
        with ephemeral_processing() as scope:
            df = scope.track(parse_tabular(file_bytes, ext))
            ...

        # 3. Async context manager:
        async with ephemeral_processing():
            content = await file.read()
            ...

        # 4. Sync/Async decorator:
        @ephemeral_processing()
        async def upload_route(...):
            ...
    """

    DEFAULT_EXCLUDE: Set[str] = {
        "self",
        "cls",
        "request",
        "response",
        "file",
        "args",
        "kwargs",
    }

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        instance = super().__new__(cls)
        # Check if used as a bare decorator: @ephemeral_processing
        if len(args) == 1 and callable(args[0]) and not kwargs:
            instance.__init__()
            return instance._wrap_fn(args[0])
        return instance

    def __init__(
        self,
        *targets: Any,
        track_locals: bool = True,
        exclude: Optional[Set[str]] = None,
        force_gc: bool = True,
        **named_targets: Any,
    ) -> None:
        self.scope = EphemeralScope()
        self.scope.register(*targets)
        self.scope.manage(**named_targets)
        self.track_locals = track_locals
        self.exclude = set(self.DEFAULT_EXCLUDE)
        if exclude:
            self.exclude.update(exclude)
        self.force_gc = force_gc

    def _cleanup_frame_locals(self, frame: Any) -> None:
        """Inspect caller frame and set intermediate objects to None."""
        if not self.track_locals or frame is None:
            return

        try:
            locals_dict = frame.f_locals
            for key, val in list(locals_dict.items()):
                if key in self.exclude or key.startswith("_"):
                    continue

                if _is_intermediate_data(val):
                    # Close if closeable
                    if hasattr(val, "close") and callable(val.close):
                        try:
                            val.close()
                        except Exception:
                            pass
                    if isinstance(val, bytearray):
                        try:
                            val.clear()
                        except Exception:
                            pass

                    # Explicitly set local reference to None
                    try:
                        locals_dict[key] = None
                    except Exception:
                        pass
        except Exception:
            pass

    def _perform_cleanup(self, frame: Optional[Any] = None) -> None:
        """Core cleanup logic executing in try/finally to guarantee gc.collect()."""
        try:
            # 1. Clear explicitly tracked objects
            self.scope.clear()

            # 2. Clear caller's frame local variables
            if frame is not None:
                self._cleanup_frame_locals(frame)
        finally:
            if self.force_gc:
                gc.collect()

    def __enter__(self) -> EphemeralScope:
        return self.scope

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        caller_frame = sys._getframe(1)
        self._perform_cleanup(caller_frame)
        return False  # Re-raise any exception

    async def __aenter__(self) -> EphemeralScope:
        return self.scope

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        caller_frame = sys._getframe(1)
        self._perform_cleanup(caller_frame)
        return False  # Re-raise any exception

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        return self._wrap_fn(fn)

    def _wrap_fn(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with self:
                    return await fn(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with self:
                    return fn(*args, **kwargs)
            return sync_wrapper
