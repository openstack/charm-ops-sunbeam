"""CeilometerServiceProvides and Requires module.

This library contains the Requires and Provides classes for handling
the ceilometer_service interface.

Import `CeilometerServiceRequires` in your charm, with the charm object and the
relation name:
    - self
    - "ceilometer_service"

Two events are also available to respond to:
    - config_changed
    - goneaway

A basic example showing the usage of this relation follows:

```
from charms.ceilometer_k8s.v0.ceilometer_service import (
    CeilometerServiceRequires
)

class CeilometerServiceClientCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        # CeilometerService Requires
        self.ceilometer_service = CeilometerServiceRequires(
            self, "ceilometer_service",
        )
        self.framework.observe(
            self.ceilometer_service.on.config_changed,
            self._on_ceilometer_service_config_changed
        )
        self.framework.observe(
            self.ceilometer_service.on.goneaway,
            self._on_ceiometer_service_goneaway
        )

    def _on_ceilometer_service_config_changed(self, event):
        '''React to the Ceilometer service config changed event.

        This event happens when CeilometerService relation is added to the
        model and relation data is changed.
        '''
        # Do something with the configuration provided by relation.
        pass

    def _on_ceilometer_service_goneaway(self, event):
        '''React to the CeilometerService goneaway event.

        This event happens when CeilometerService relation is removed.
        '''
        # CeilometerService Relation has goneaway.
        pass
```
"""

import logging
from typing import (
    Optional,
)

from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationEvent,
)
from ops.framework import (
    EventSource,
    Object,
    ObjectEvents,
)
from ops.model import (
    Relation,
)

logger = logging.getLogger(__name__)


# The unique Charmhub library identifier, never change it
LIBID = "fcbb94e7a18740729eaf9e2c3b90017f"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


class CeilometerConfigRequestEvent(RelationEvent):
    """CeilometerConfigRequest Event."""

    pass


class CeilometerServiceProviderEvents(ObjectEvents):
    """Events class for `on`."""

    config_request = EventSource(CeilometerConfigRequestEvent)


class CeilometerServiceProvides(Object):
    """CeilometerServiceProvides class."""

    on = CeilometerServiceProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_ceilometer_service_relation_changed,
        )

    def _on_ceilometer_service_relation_changed(
        self, event: RelationChangedEvent
    ):
        """Handle CeilometerService relation changed."""
        logging.debug("CeilometerService relation changed")
        self.on.config_request.emit(event.relation)

    def set_config(
        self, relation: Optional[Relation], telemetry_secret: str
    ) -> None:
        """Set ceilometer configuration on the relation."""
        if not self.charm.unit.is_leader():
            logging.debug("Not a leader unit, skipping set config")
            return

        # If relation is not provided send config to all the related
        # applications. This happens usually when config data is
        # updated by provider and wants to send the data to all
        # related applications
        if relation is None:
            logging.debug(
                "Sending config to all related applications of relation"
                f"{self.relation_name}"
            )
            for relation in self.framework.model.relations[self.relation_name]:
                relation.data[self.charm.app][
                    "telemetry-secret"
                ] = telemetry_secret
        else:
            logging.debug(
                f"Sending config on relation {relation.app.name} "
                f"{relation.name}/{relation.id}"
            )
            relation.data[self.charm.app][
                "telemetry-secret"
            ] = telemetry_secret


class CeilometerConfigChangedEvent(RelationEvent):
    """CeilometerConfigChanged Event."""

    pass


class CeilometerServiceGoneAwayEvent(RelationEvent):
    """CeilometerServiceGoneAway Event."""

    pass


class CeilometerServiceRequirerEvents(ObjectEvents):
    """Events class for `on`."""

    config_changed = EventSource(CeilometerConfigChangedEvent)
    goneaway = EventSource(CeilometerServiceGoneAwayEvent)


class CeilometerServiceRequires(Object):
    """CeilometerServiceRequires class."""

    on = CeilometerServiceRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_ceilometer_service_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_ceilometer_service_relation_broken,
        )

    def _on_ceilometer_service_relation_changed(
        self, event: RelationChangedEvent
    ):
        """Handle CeilometerService relation changed."""
        logging.debug("CeilometerService config data changed")
        self.on.config_changed.emit(event.relation)

    def _on_ceilometer_service_relation_broken(
        self, event: RelationBrokenEvent
    ):
        """Handle CeilometerService relation changed."""
        logging.debug("CeilometerService on_broken")
        self.on.goneaway.emit(event.relation)

    @property
    def _ceilometer_service_rel(self) -> Optional[Relation]:
        """The ceilometer service relation."""
        return self.framework.model.get_relation(self.relation_name)

    def get_remote_app_data(self, key: str) -> Optional[str]:
        """Return the value for the given key from remote app data."""
        if self._ceilometer_service_rel:
            data = self._ceilometer_service_rel.data[
                self._ceilometer_service_rel.app
            ]
            return data.get(key)

        return None

    @property
    def telemetry_secret(self) -> Optional[str]:
        """Return the telemetry_secret."""
        return self.get_remote_app_data("telemetry-secret")
