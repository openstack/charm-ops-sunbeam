"""IdentityServiceProvides and Requires module.


This library contains the Requires and Provides classes for handling
the identity_service interface.

Import `IdentityServiceRequires` in your charm, with the charm object and the
relation name:
    - self
    - "identity_service"

Also provide additional parameters to the charm object:
    - service
    - internal_url
    - public_url
    - admin_url
    - region
    - username
    - vhost

Two events are also available to respond to:
    - connected
    - ready
    - goneaway

A basic example showing the usage of this relation follows:

```
from charms.sunbeam_sunbeam_identity_service_operator.v0.identity_service import IdentityServiceRequires

class IdentityServiceClientCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        # IdentityService Requires
        self.identity_service = IdentityServiceRequires(
            self, "identity_service",
            service = "my-service"
            internal_url = "http://internal-url"
            public_url = "http://public-url"
            admin_url = "http://admin-url"
            region = "region"
        )
        self.framework.observe(
            self.identity_service.on.connected, self._on_identity_service_connected)
        self.framework.observe(
            self.identity_service.on.ready, self._on_identity_service_ready)
        self.framework.observe(
            self.identity_service.on.goneaway, self._on_identity_service_goneaway)

    def _on_identity_service_connected(self, event):
        '''React to the IdentityService connected event.

        This event happens when n IdentityService relation is added to the
        model before credentials etc have been provided.
        '''
        # Do something before the relation is complete
        pass

    def _on_identity_service_ready(self, event):
        '''React to the IdentityService ready event.

        The IdentityService interface will use the provided config for the
        request to the identity server.
        '''
        # IdentityService Relation is ready. Do something with the completed relation.
        pass

    def _on_identity_service_goneaway(self, event):
        '''React to the IdentityService goneaway event.

        This event happens when an IdentityService relation is removed.
        '''
        # IdentityService Relation has goneaway. shutdown services or suchlike
        pass
```
"""

# The unique Charmhub library identifier, never change it
LIBID = "deadbeef"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

import json
import logging
import requests

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


class CloudCredentialsConnectedEvent(EventBase):
    """CloudCredentials connected Event."""

    pass


class CloudCredentialsReadyEvent(EventBase):
    """CloudCredentials ready for use Event."""

    pass


class CloudCredentialsGoneAwayEvent(EventBase):
    """CloudCredentials relation has gone-away Event"""

    pass


class CloudCredentialsServerEvents(ObjectEvents):
    """Events class for `on`"""

    connected = EventSource(CloudCredentialsConnectedEvent)
    ready = EventSource(CloudCredentialsReadyEvent)
    goneaway = EventSource(CloudCredentialsGoneAwayEvent)


class CloudCredentialsRequires(Object):
    """
    CloudCredentialsRequires class
    """

    on = CloudCredentialsServerEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name: str):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_cloud_credentials_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_cloud_credentials_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_departed,
            self._on_cloud_credentials_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_cloud_credentials_relation_broken,
        )

    def _on_cloud_credentials_relation_joined(self, event):
        """CloudCredentials relation joined."""
        logging.debug("CloudCredentials on_joined")
        self.on.connected.emit()
        self.request_credentials()

    def _on_cloud_credentials_relation_changed(self, event):
        """CloudCredentials relation changed."""
        logging.debug("CloudCredentials on_changed")
        try:
            self.on.ready.emit()
        except AttributeError:
            logger.exception('Error when emitting event')

    def _on_cloud_credentials_relation_broken(self, event):
        """CloudCredentials relation broken."""
        logging.debug("CloudCredentials on_broken")
        self.on.goneaway.emit()

    @property
    def _cloud_credentials_rel(self) -> Relation:
        """The CloudCredentials relation."""
        return self.framework.model.get_relation(self.relation_name)

    def get_remote_app_data(self, key: str) -> str:
        """Return the value for the given key from remote app data."""
        data = self._cloud_credentials_rel.data[self._cloud_credentials_rel.app]
        return data.get(key)

    @property
    def api_version(self) -> str:
        """Return the api_version."""
        return self.get_remote_app_data('api-version')

    @property
    def auth_host(self) -> str:
        """Return the auth_host."""
        return self.get_remote_app_data('auth-host')

    @property
    def auth_port(self) -> str:
        """Return the auth_port."""
        return self.get_remote_app_data('auth-port')

    @property
    def auth_protocol(self) -> str:
        """Return the auth_protocol."""
        return self.get_remote_app_data('auth-protocol')

    @property
    def internal_host(self) -> str:
        """Return the internal_host."""
        return self.get_remote_app_data('internal-host')

    @property
    def internal_port(self) -> str:
        """Return the internal_port."""
        return self.get_remote_app_data('internal-port')

    @property
    def internal_protocol(self) -> str:
        """Return the internal_protocol."""
        return self.get_remote_app_data('internal-protocol')

    @property
    def username(self) -> str:
        """Return the username."""
        return self.get_remote_app_data('username')

    @property
    def password(self) -> str:
        """Return the password."""
        return self.get_remote_app_data('password')

    @property
    def project_name(self) -> str:
        """Return the project name."""
        return self.get_remote_app_data('project-name')

    @property
    def project_id(self) -> str:
        """Return the project id."""
        return self.get_remote_app_data('project-id')

    @property
    def user_domain_name(self) -> str:
        """Return the name of the user domain."""
        return self.get_remote_app_data('user-domain-name')

    @property
    def user_domain_id(self) -> str:
        """Return the id of the user domain."""
        return self.get_remote_app_data('user-domain-id')

    @property
    def project_domain_name(self) -> str:
        """Return the name of the project domain."""
        return self.get_remote_app_data('project-domain-name')

    @property
    def project_domain_id(self) -> str:
        """Return the id of the project domain."""
        return self.get_remote_app_data('project-domain-id')

    @property
    def region(self) -> str:
        """Return the region for the auth urls."""
        return self.get_remote_app_data('region')

    def request_credentials(self) -> None:
        """Request credentials from the CloudCredentials server."""
        if self.model.unit.is_leader():
            logging.debug(f'Requesting credentials for {self.charm.app.name}')
            app_data = self._cloud_credentials_rel.data[self.charm.app]
            app_data['username'] = self.charm.app.name


class HasCloudCredentialsClientsEvent(EventBase):
    """Has CloudCredentialsClients Event."""

    pass


class ReadyCloudCredentialsClientsEvent(EventBase):
    """CloudCredentialsClients Ready Event."""

    def __init__(self, handle, relation_id, relation_name, username):
        super().__init__(handle)
        self.relation_id = relation_id
        self.relation_name = relation_name
        self.username = username

    def snapshot(self):
        return {
            "relation_id": self.relation_id,
            "relation_name": self.relation_name,
            "username": self.username,
        }

    def restore(self, snapshot):
        super().restore(snapshot)
        self.relation_id = snapshot["relation_id"]
        self.relation_name = snapshot["relation_name"]
        self.username = snapshot["username"]


class CloudCredentialsClientsGoneAwayEvent(EventBase):
    """Has CloudCredentialsClientsGoneAwayEvent Event."""

    pass


class CloudCredentialsClientEvents(ObjectEvents):
    """Events class for `on`"""

    has_cloud_credentials_clients = EventSource(
        HasCloudCredentialsClientsEvent
    )
    ready_cloud_credentials_clients = EventSource(
        ReadyCloudCredentialsClientsEvent
    )
    cloud_credentials_clients_gone = EventSource(
        CloudCredentialsClientsGoneAwayEvent
    )


class CloudCredentialsProvides(Object):
    """
    CloudCredentialsProvides class
    """

    on = CloudCredentialsClientEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._on_cloud_credentials_relation_joined,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_cloud_credentials_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_cloud_credentials_relation_broken,
        )

    def _on_cloud_credentials_relation_joined(self, event):
        """Handle CloudCredentials joined."""
        logging.debug("CloudCredentialsProvides on_joined")
        self.on.has_cloud_credentials_clients.emit()

    def _on_cloud_credentials_relation_changed(self, event):
        """Handle CloudCredentials changed."""
        logging.debug("CloudCredentials on_changed")
        REQUIRED_KEYS = ['username']

        values = [
            event.relation.data[event.relation.app].get(k)
            for k in REQUIRED_KEYS
        ]
        # Validate data on the relation
        if all(values):
            username = event.relation.data[event.relation.app]['username']
            self.on.ready_cloud_credentials_clients.emit(
                event.relation.id,
                event.relation.name,
                username,
            )

    def _on_cloud_credentials_relation_broken(self, event):
        """Handle CloudCredentials broken."""
        logging.debug("CloudCredentialsProvides on_departed")
        self.on.cloud_credentials_clients_gone.emit()

    def set_cloud_credentials(self, relation_name: int,
                              relation_id: str,
                              api_version: str,
                              auth_host: str,
                              auth_port: str,
                              auth_protocol: str,
                              internal_host: str,
                              internal_port: str,
                              internal_protocol: str,
                              username: str,
                              password: str,
                              project_name: str,
                              project_id: str,
                              user_domain_name: str,
                              user_domain_id: str,
                              project_domain_name: str,
                              project_domain_id: str,
                              region: str):
        logging.debug("Setting cloud_credentials connection information.")
        for relation in self.framework.model.relations[relation_name]:
            if relation.id == relation_id:
                _cloud_credentials_rel = relation
        app_data = _cloud_credentials_rel.data[self.charm.app]
        app_data["api-version"] = api_version
        app_data["auth-host"] = auth_host
        app_data["auth-port"] = str(auth_port)
        app_data["auth-protocol"] = auth_protocol
        app_data["internal-host"] = internal_host
        app_data["internal-port"] = str(internal_port)
        app_data["internal-protocol"] = internal_protocol
        app_data["username"] = username
        app_data["password"] = password
        app_data["project-name"] = project_name
        app_data["project-id"] = project_id
        app_data["user-domain-name"] = user_domain_name
        app_data["user-domain-id"] = user_domain_id
        app_data["project-domain-name"] = project_domain_name
        app_data["project-domain-id"] = project_domain_id
        app_data["region"] = region
