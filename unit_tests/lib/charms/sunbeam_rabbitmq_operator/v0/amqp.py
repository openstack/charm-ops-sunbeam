"""AMQPProvides and Requires module.


This library contains the Requires and Provides classes for handling
the amqp interface.

Import `AMQPRequires` in your charm, with the charm object and the
relation name:
    - self
    - "amqp"

Also provide two additional parameters to the charm object:
    - username
    - vhost

Two events are also available to respond to:
    - connected
    - ready
    - goneaway

A basic example showing the usage of this relation follows:

```
from charms.sunbeam_rabbitmq_operator.v0.amqp import AMQPRequires

class AMQPClientCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        # AMQP Requires
        self.amqp = AMQPRequires(
            self, "amqp",
            username="myusername",
            vhost="vhostname"
        )
        self.framework.observe(
            self.amqp.on.connected, self._on_amqp_connected)
        self.framework.observe(
            self.amqp.on.ready, self._on_amqp_ready)
        self.framework.observe(
            self.amqp.on.goneaway, self._on_amqp_goneaway)

    def _on_amqp_connected(self, event):
        '''React to the AMQP connected event.

        This event happens when n AMQP relation is added to the
        model before credentials etc have been provided.
        '''
        # Do something before the relation is complete
        pass

    def _on_amqp_ready(self, event):
        '''React to the AMQP ready event.

        The AMQP interface will use the provided username and vhost for the
        request to the rabbitmq server.
        '''
        # AMQP Relation is ready. Do something with the completed relation.
        pass

    def _on_amqp_goneaway(self, event):
        '''React to the AMQP goneaway event.

        This event happens when an AMQP relation is removed.
        '''
        # AMQP Relation has goneaway. shutdown services or suchlike
        pass
```
"""

# The unique Charmhub library identifier, never change it
LIBID = "ab1414b6baf044f099caf9c117f1a101"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 4

import logging

from ops.framework import (
    StoredState,
    EventBase,
    ObjectEvents,
    EventSource,
    Object,
)

from ops.model import Relation

from typing import List

logger = logging.getLogger(__name__)


class AMQPConnectedEvent(EventBase):
    """AMQP connected Event."""

    pass


class AMQPReadyEvent(EventBase):
    """AMQP ready for use Event."""

    pass


class AMQPGoneAwayEvent(EventBase):
    """AMQP relation has gone-away Event"""

    pass


class AMQPServerEvents(ObjectEvents):
    """Events class for `on`"""

    connected = EventSource(AMQPConnectedEvent)
    ready = EventSource(AMQPReadyEvent)
    goneaway = EventSource(AMQPGoneAwayEvent)


class AMQPRequires(Object):
    """
    AMQPRequires class
    """

    on = AMQPServerEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name: str, username: str, vhost: str):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.username = username
        self.vhost = vhost
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_amqp_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_amqp_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_departed,
            self._on_amqp_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_amqp_relation_broken,
        )

    def _on_amqp_relation_joined(self, event):
        """AMQP relation joined."""
        logging.debug("RabbitMQAMQPRequires on_joined")
        self.on.connected.emit()
        self.request_access(self.username, self.vhost)

    def _on_amqp_relation_changed(self, event):
        """AMQP relation changed."""
        logging.debug("RabbitMQAMQPRequires on_changed/departed")
        if self.password:
            self.on.ready.emit()

    def _on_amqp_relation_broken(self, event):
        """AMQP relation broken."""
        logging.debug("RabbitMQAMQPRequires on_broken")
        self.on.goneaway.emit()

    @property
    def _amqp_rel(self) -> Relation:
        """The AMQP relation."""
        return self.framework.model.get_relation(self.relation_name)

    @property
    def password(self) -> str:
        """Return the AMQP password from the server side of the relation."""
        return self._amqp_rel.data[self._amqp_rel.app].get("password")

    @property
    def hostname(self) -> str:
        """Return the hostname from the AMQP relation"""
        return self._amqp_rel.data[self._amqp_rel.app].get("hostname")

    @property
    def ssl_port(self) -> str:
        """Return the SSL port from the AMQP relation"""
        return self._amqp_rel.data[self._amqp_rel.app].get("ssl_port")

    @property
    def ssl_ca(self) -> str:
        """Return the SSL port from the AMQP relation"""
        return self._amqp_rel.data[self._amqp_rel.app].get("ssl_ca")

    @property
    def hostnames(self) -> List[str]:
        """Return a list of remote RMQ hosts from the AMQP relation"""
        _hosts = []
        for unit in self._amqp_rel.units:
            _hosts.append(self._amqp_rel.data[unit].get("ingress-address"))
        return _hosts

    def request_access(self, username: str, vhost: str) -> None:
        """Request access to the AMQP server."""
        if self.model.unit.is_leader():
            logging.debug("Requesting AMQP user and vhost")
            self._amqp_rel.data[self.charm.app]["username"] = username
            self._amqp_rel.data[self.charm.app]["vhost"] = vhost


class HasAMQPClientsEvent(EventBase):
    """Has AMQPClients Event."""

    pass


class ReadyAMQPClientsEvent(EventBase):
    """AMQPClients Ready Event."""

    pass


class AMQPClientEvents(ObjectEvents):
    """Events class for `on`"""

    has_amqp_clients = EventSource(HasAMQPClientsEvent)
    ready_amqp_clients = EventSource(ReadyAMQPClientsEvent)


class AMQPProvides(Object):
    """
    AMQPProvides class
    """

    on = AMQPClientEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name, callback):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.callback = callback
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_amqp_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_amqp_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_amqp_relation_broken,
        )

    def _on_amqp_relation_joined(self, event):
        """Handle AMQP joined."""
        logging.debug("RabbitMQAMQPProvides on_joined data={}"
                      .format(event.relation.data))
        self.on.has_amqp_clients.emit()

    def _on_amqp_relation_changed(self, event):
        """Handle AMQP changed."""
        logging.debug("RabbitMQAMQPProvides on_changed data={}"
                      .format(event.relation.data))
        # Validate data on the relation
        if self.username(event) and self.vhost(event):
            self.on.ready_amqp_clients.emit()
            if self.charm.unit.is_leader():
                self.callback(event, self.username(event), self.vhost(event))
        else:
            logging.warning("Received AMQP changed event without the "
                            "expected keys ('username', 'vhost') in the "
                            "application data bag.  Incompatible charm in "
                            "other end of relation?")

    def _on_amqp_relation_broken(self, event):
        """Handle AMQP broken."""
        logging.debug("RabbitMQAMQPProvides on_departed")
        # TODO clear data on the relation

    def username(self, event):
        """Return the AMQP username from the client side of the relation."""
        return event.relation.data[event.relation.app].get("username")

    def vhost(self, event):
        """Return the AMQP vhost from the client side of the relation."""
        return event.relation.data[event.relation.app].get("vhost")
