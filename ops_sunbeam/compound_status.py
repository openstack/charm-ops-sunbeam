"""
A mini library for tracking status messages.

We want this because keeping track of everything
with a single unit.status is too difficult.

The user will still see a single status and message
(one deemed to be the highest priority),
but the charm can easily set the status of various
aspects of the application without clobbering other parts.
"""
import json
import logging
from typing import Callable, Dict, Tuple, Optional

from ops.charm import CharmBase
from ops.framework import Handle, Object, StoredStateData, CommitEvent
from ops.model import ActiveStatus, StatusBase, UnknownStatus, WaitingStatus
from ops.storage import NoSnapshotError

logger = logging.getLogger(__name__)

STATUS_PRIORITIES = {
    "blocked": 1,
    "waiting": 2,
    "maintenance": 3,
    "active": 4,
    "unknown": 5,
}


class Status:
    """
    An atomic status.

    A wrapper around a StatusBase from ops,
    that adds a priority, label,
    and methods for use with a pool of statuses.
    """

    def __init__(self, label: str, priority: int = 0) -> None:
        """
        Create a new Status object.

        label: string label
        priority: integer, higher number is higher priority, default is 0
        """
        self.label: str = label
        self._priority: int = priority
        self.never_set = True

        # The actual status of this Status object.
        # Use `self.set(...)` to update it.
        self.status: StatusBase = UnknownStatus()

        # if on_update is set,
        # it will be called as a function with no arguments
        # whenever the status is set.
        self.on_update: Optional[Callable[[], None]] = None

    def set(self, status: StatusBase) -> None:
        """
        Set the status.

        Will also run the on_update hook if available
        (should be set by the pool so the pool knows when it should update).
        """
        self.status = status
        self.never_set = False
        if self.on_update is not None:
            self.on_update()

    def message(self) -> str:
        """
        Get the status message consistently.

        Useful because UnknownStatus has no message attribute.
        """
        if self.status.name == "unknown":
            return ""
        return self.status.message

    def priority(self) -> Tuple[int, int]:
        """
        Return a value to use for sorting statuses by priority.

        Used by the pool to retrieve the highest priority status
        to display to the user.
        """
        return STATUS_PRIORITIES[self.status.name], -self._priority

    def _serialize(self) -> dict:
        """Serialize Status for storage."""
        return {
            "status": self.status.name,
            "message": self.message(),
        }


class StatusPool(Object):
    """
    A pool of Status objects.

    This is implemented as an `Object`,
    so we can more simply save state between hook executions.
    """

    def __init__(self, charm: CharmBase) -> None:
        """
        Init the status pool and restore from stored state if available.

        Note that instantiating more than one StatusPool here is not supported,
        due to hardcoded framework stored data IDs.
        If we want that in the future,
        we'll need to generate a custom deterministic ID.
        I can't think of any cases where
        more than one StatusPool is required though...
        """
        super().__init__(charm, "status_pool")
        self._pool: Dict[str, Status] = {}
        self._charm = charm

        # Restore info from the charm's state.
        # We need to do this on init,
        # so we can retain previous statuses that were set.
        charm.framework.register_type(
            StoredStateData, self, StoredStateData.handle_kind
        )
        stored_handle = Handle(
            self, StoredStateData.handle_kind, "_status_pool"
        )

        try:
            self._state = charm.framework.load_snapshot(stored_handle)
            status_state = json.loads(self._state["statuses"])
        except NoSnapshotError:
            self._state = StoredStateData(self, "_status_pool")
            status_state = []
        self._status_state = status_state

        # 'commit' is an ops framework event
        # that tells the object to save a snapshot of its state for later.
        charm.framework.observe(charm.framework.on.commit, self._on_commit)

    def add(self, status: Status) -> None:
        """
        Idempotently add a status object to the pool.

        Reconstitute from saved state if it's a new status.
        """
        if (
            status.never_set and
            status.label in self._status_state and
            status.label not in self._pool
        ):
            # If this status hasn't been seen or set yet,
            # and we have saved state for it,
            # then reconstitute it.
            # This allows us to retain statuses across hook invocations.
            saved = self._status_state[status.label]
            status.status = StatusBase.from_name(
                saved["status"],
                saved["message"],
            )

        self._pool[status.label] = status
        status.on_update = self.on_update
        self.on_update()

    def summarise(self) -> str:
        """
        Return a human readable summary of all the statuses in the pool.

        Will be a multi-line string.
        """
        lines = []
        for status in sorted(self._pool.values(), key=lambda x: x.priority()):
            lines.append("{label:>30}: {status:>10} | {message}".format(
                label=status.label,
                message=status.message(),
                status=status.status.name,
            ))

        return "\n".join(lines)

    def _on_commit(self, _event: CommitEvent) -> None:
        """
        Store the current state of statuses.

        So we can restore them on the next run of the charm.
        """
        self._state["statuses"] = json.dumps(
            {
                status.label: status._serialize()
                for status in self._pool.values()
            }
        )
        self._charm.framework.save_snapshot(self._state)
        self._charm.framework._storage.commit()

    def on_update(self) -> None:
        """
        Update the unit status with the current highest priority status.

        Use as a hook to run whenever a status is updated in the pool.
        """
        status = (
            sorted(self._pool.values(), key=lambda x: x.priority())[0]
            if self._pool
            else None
        )
        if status is None or status.status.name == "unknown":
            self._charm.unit.status = WaitingStatus("no status set yet")
        elif status.status.name == "active" and not status.message():
            # Avoid status name prefix if everything is active with no message.
            # If there's a message, then we want the prefix
            # to help identify where the message originates.
            self._charm.unit.status = ActiveStatus("")
        else:
            message = status.message()
            self._charm.unit.status = StatusBase.from_name(
                status.status.name,
                "({}){}".format(
                    status.label,
                    " " + message if message else "",
                )
            )
