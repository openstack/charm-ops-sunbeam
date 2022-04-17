"""TODO: Add a proper docstring here.

This is a placeholder docstring for this charm library. Docstrings are
presented on Charmhub and updated whenever you push a new version of the
library.

Complete documentation about creating and documenting libraries can be found
in the SDK docs at https://juju.is/docs/sdk/libraries.

See `charmcraft publish-lib` and `charmcraft fetch-lib` for details of how to
share and consume charm libraries. They serve to enhance collaboration
between charmers. Use a charmer's libraries for classes that handle
integration with their charm.

Bear in mind that new revisions of the different major API versions (v0, v1,
v2 etc) are maintained independently.  You can continue to update v0 and v1
after you have pushed v3.

Markdown is supported, following the CommonMark specification.
"""

import logging
import typing
from ops.framework import (
    StoredState,
    EventBase,
    ObjectEvents,
    EventSource,
    Object,
)

# The unique Charmhub library identifier, never change it
LIBID = "19e5a5857acd4a94a4a759d173d18232"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2


# TODO: add your code here! Happy coding!
class OVSDBCMSConnectedEvent(EventBase):
    """OVSDBCMS connected Event."""

    pass


class OVSDBCMSReadyEvent(EventBase):
    """OVSDBCMS ready for use Event."""

    pass


class OVSDBCMSGoneAwayEvent(EventBase):
    """OVSDBCMS relation has gone-away Event"""

    pass


class OVSDBCMSServerEvents(ObjectEvents):
    """Events class for `on`"""

    connected = EventSource(OVSDBCMSConnectedEvent)
    ready = EventSource(OVSDBCMSReadyEvent)
    goneaway = EventSource(OVSDBCMSGoneAwayEvent)


class OVSDBCMSRequires(Object):
    """
    OVSDBCMSRequires class
    """

    on = OVSDBCMSServerEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name: str):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_ovsdb_cms_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_ovsdb_cms_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_departed,
            self._on_ovsdb_cms_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_ovsdb_cms_relation_broken,
        )

    def _on_ovsdb_cms_relation_joined(self, event):
        """OVSDBCMS relation joined."""
        logging.debug("OVSDBCMSRequires on_joined")
        self.on.connected.emit()

    def bound_addresses(self):
        return self.get_all_unit_values("bound-address")

    def remote_ready(self):
        return all(self.bound_addresses())

    def _on_ovsdb_cms_relation_changed(self, event):
        """OVSDBCMS relation changed."""
        logging.debug("OVSDBCMSRequires on_changed")
        if self.remote_ready():
            self.on.ready.emit()

    def _on_ovsdb_cms_relation_broken(self, event):
        """OVSDBCMS relation broken."""
        logging.debug("OVSDBCMSRequires on_broken")
        self.on.goneaway.emit()

    def get_all_unit_values(self, key: str) -> typing.List[str]:
        """Retrieve value for key from all related units."""
        values = []
        relation = self.framework.model.get_relation(self.relation_name)
        if relation:
            for unit in relation.units:
                values.append(relation.data[unit].get(key))
        return values



class OVSDBCMSClientConnectedEvent(EventBase):
    """OVSDBCMS connected Event."""

    pass


class OVSDBCMSClientReadyEvent(EventBase):
    """OVSDBCMS ready for use Event."""

    pass


class OVSDBCMSClientGoneAwayEvent(EventBase):
    """OVSDBCMS relation has gone-away Event"""

    pass


class OVSDBCMSClientEvents(ObjectEvents):
    """Events class for `on`"""

    connected = EventSource(OVSDBCMSClientConnectedEvent)
    ready = EventSource(OVSDBCMSClientReadyEvent)
    goneaway = EventSource(OVSDBCMSClientGoneAwayEvent)


class OVSDBCMSProvides(Object):
    """
    OVSDBCMSProvides class
    """

    on = OVSDBCMSClientEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_ovsdb_cms_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_ovsdb_cms_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_ovsdb_cms_relation_broken,
        )

    def _on_ovsdb_cms_relation_joined(self, event):
        """Handle ovsdb-cms joined."""
        logging.debug("OVSDBCMSProvides on_joined")
        self.on.connected.emit()

    def _on_ovsdb_cms_relation_changed(self, event):
        """Handle ovsdb-cms changed."""
        logging.debug("OVSDBCMSProvides on_changed")
        self.on.ready.emit()

    def _on_ovsdb_cms_relation_broken(self, event):
        """Handle ovsdb-cms broken."""
        logging.debug("OVSDBCMSProvides on_departed")
        self.on.goneaway.emit()

    def set_unit_data(self, settings: typing.Dict[str, str]) -> None:
        """Publish settings on the peer unit data bag."""
        relations = self.framework.model.relations[self.relation_name]
        for relation in relations:
            for k, v in settings.items():
                relation.data[self.model.unit][k] = v

