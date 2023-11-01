# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Base classes for defining a charm using the Operator framework."""

import hashlib
import json
import logging
import secrets
import string
from typing import (
    Callable,
    Dict,
    FrozenSet,
    List,
    Optional,
    Tuple,
    Union,
)
from urllib.parse import (
    urlparse,
)

import ops.charm
import ops.framework
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    SecretNotFoundError,
    UnknownStatus,
    WaitingStatus,
)

import ops_sunbeam.compound_status as compound_status
import ops_sunbeam.interfaces as sunbeam_interfaces

logger = logging.getLogger(__name__)

ERASURE_CODED = "erasure-coded"
REPLICATED = "replicated"


class RelationHandler(ops.charm.Object):
    """Base handler class for relations.

    A relation handler is used to manage a charms interaction with a relation
    interface. This includes:

    1) Registering handlers to process events from the interface. The last
       step of these handlers is to make a callback to a specified method
       within the charm `callback_f`
    2) Expose a `ready` property so the charm can check a relations readiness
    3) A `context` method which returns a dict which pulls together data
       received and sent on an interface.
    """

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        super().__init__(
            charm,
            # Ensure we can have multiple instances of a relation handler,
            # but only one per relation.
            key=type(self).__name__ + "_" + relation_name,
        )
        self.charm = charm
        self.relation_name = relation_name
        self.callback_f = callback_f
        self.interface = self.setup_event_handler()
        self.mandatory = mandatory
        self.status = compound_status.Status(self.relation_name)
        self.charm.status_pool.add(self.status)
        self.set_status(self.status)

    def set_status(self, status: compound_status.Status) -> None:
        """Set the status based on current state.

        Will be called once, during construction,
        after everything else is initialised.
        Override this in a child class if custom logic should be used.
        """
        if not self.model.relations.get(self.relation_name):
            if self.mandatory:
                status.set(BlockedStatus("integration missing"))
            else:
                status.set(UnknownStatus())
        elif self.ready:
            status.set(ActiveStatus(""))
        else:
            status.set(WaitingStatus("integration incomplete"))

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for the relation.

        This method must be overridden in concrete class
        implementations.
        """
        raise NotImplementedError

    def get_interface(self) -> Tuple[ops.charm.Object, str]:
        """Return the interface that this handler encapsulates.

        This is a combination of the interface object and the
        name of the relation its wired into.
        """
        return self.interface, self.relation_name

    def interface_properties(self) -> dict:
        """Extract properties of the interface."""
        property_names = [
            p
            for p in dir(self.interface)
            if isinstance(getattr(type(self.interface), p, None), property)
        ]
        properties = {
            p: getattr(self.interface, p)
            for p in property_names
            if not p.startswith("_") and p not in ["model"]
        }
        return properties

    @property
    def ready(self) -> bool:
        """Determine with the relation is ready for use."""
        raise NotImplementedError

    def context(self) -> dict:
        """Pull together context for rendering templates."""
        return self.interface_properties()

    def update_relation_data(self):
        """Update relation outside of relation context."""
        raise NotImplementedError


class IngressHandler(RelationHandler):
    """Base class to handle Ingress relations."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        service_name: str,
        default_ingress_port: int,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.default_ingress_port = default_ingress_port
        self.service_name = service_name
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Ingress relation."""
        logger.debug("Setting up ingress event handler")
        from charms.traefik_k8s.v2.ingress import (
            IngressPerAppRequirer,
        )

        interface = IngressPerAppRequirer(
            self.charm,
            self.relation_name,
            port=self.default_ingress_port,
        )
        self.framework.observe(interface.on.ready, self._on_ingress_ready)
        self.framework.observe(interface.on.revoked, self._on_ingress_revoked)
        return interface

    def _on_ingress_ready(self, event) -> None:  # noqa: ANN001
        """Handle ingress relation changed events.

        `event` is an instance of
        `charms.traefik_k8s.v2.ingress.IngressPerAppReadyEvent`.
        """
        url = self.url
        logger.debug(f"Received url: {url}")
        if not url:
            return

        self.callback_f(event)

    def _on_ingress_revoked(self, event) -> None:  # noqa: ANN001
        """Handle ingress relation revoked event.

        `event` is an instance of
        `charms.traefik_k8s.v2.ingress.IngressPerAppRevokedEvent`
        """
        # Callback call to update keystone endpoints
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    @property
    def ready(self) -> bool:
        """Whether the handler is ready for use."""
        from charms.traefik_k8s.v2.ingress import (
            DataValidationError,
        )

        try:
            url = self.interface.url
        except DataValidationError:
            logger.debug(
                "Failed to fetch relation's url,"
                " the root cause might a change to V2 Ingress, "
                "in this case, this error should go away.",
                exc_info=True,
            )
            return False

        if url:
            return True

        return False

    @property
    def url(self) -> Optional[str]:
        """Return the URL used by the remote ingress service."""
        if not self.ready:
            return None

        return self.interface.url

    def context(self) -> dict:
        """Context containing ingress data."""
        parse_result = urlparse(self.url)
        return {
            "ingress_path": parse_result.path,
        }


class IngressInternalHandler(IngressHandler):
    """Handler for Ingress relations on internal interface."""


class IngressPublicHandler(IngressHandler):
    """Handler for Ingress relations on public interface."""


class DBHandler(RelationHandler):
    """Handler for DB relations."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        database: str,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        # a database name as requested by the charm.
        self.database_name = database
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for a MySQL relation."""
        logger.debug("Setting up DB event handler")
        # Import here to avoid import errors if ops_sunbeam is being used
        # with a charm that doesn't want a DBHandler
        # and doesn't install this database_requires library.
        from charms.data_platform_libs.v0.database_requires import (
            DatabaseRequires,
        )

        # Alias is required to events for this db
        # from trigger handlers for other dbs.
        # It also must be a valid python identifier.
        alias = self.relation_name.replace("-", "_")
        db = DatabaseRequires(
            self.charm,
            self.relation_name,
            self.database_name,
            relations_aliases=[alias],
        )
        self.framework.observe(
            # db.on[f"{alias}_database_created"], # this doesn't work because:
            # RuntimeError: Framework.observe requires a BoundEvent as
            # second parameter, got <ops.framework.PrefixedEvents object ...
            getattr(db.on, f"{alias}_database_created"),
            self._on_database_updated,
        )
        self.framework.observe(
            getattr(db.on, f"{alias}_endpoints_changed"),
            self._on_database_updated,
        )

        # Gone away events are not handled by the database interface library.
        # So handle them in this class
        self.framework.observe(
            self.charm.on[self.relation_name].relation_broken,
            self._on_database_relation_broken,
        )

        # this will be set to self.interface in parent class
        return db

    def _on_database_updated(self, event: ops.framework.EventBase) -> None:
        """Handle database change events."""
        if not (event.username or event.password or event.endpoints):
            return

        data = event.relation.data[event.relation.app]
        display_data = {k: v for k, v in data.items()}
        if "password" in display_data:
            display_data["password"] = "REDACTED"
        logger.info(f"Received data: {display_data}")
        self.callback_f(event)

    def _on_database_relation_broken(
        self, event: ops.framework.EventBase
    ) -> None:
        """Handle database gone away event."""
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    def get_relation_data(self) -> dict:
        """Load the data from the relation for consumption in the handler."""
        if len(self.interface.relations) > 0:
            return self.interface.relations[0].data[
                self.interface.relations[0].app
            ]
        return {}

    @property
    def ready(self) -> bool:
        """Whether the handler is ready for use."""
        data = self.get_relation_data()
        return bool(
            data.get("endpoints")
            and data.get("username")
            and data.get("password")
        )

    def context(self) -> dict:
        """Context containing database connection data."""
        if not self.ready:
            return {}

        data = self.get_relation_data()
        database_name = self.database_name
        database_host = data["endpoints"]
        database_user = data["username"]
        database_password = data["password"]
        database_type = "mysql+pymysql"
        has_tls = data.get("tls")
        tls_ca = data.get("tls-ca")

        connection = (
            f"{database_type}://{database_user}:{database_password}"
            f"@{database_host}/{database_name}"
        )
        if has_tls:
            connection = connection + f"?ssl_ca={tls_ca}"

        # This context ends up namespaced under the relation name
        # (normalised to fit a python identifier - s/-/_/),
        # and added to the context for jinja templates.
        # eg. if this DBHandler is added with relation name api-database,
        # the database connection string can be obtained in templates with
        # `api_database.connection`.
        return {
            "database": database_name,
            "database_host": database_host,
            "database_password": database_password,
            "database_user": database_user,
            "database_type": database_type,
            "connection": connection,
        }


class RabbitMQHandler(RelationHandler):
    """Handler for managing a rabbitmq relation."""

    DEFAULT_PORT = "5672"

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        username: str,
        vhost: int,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.username = username
        self.vhost = vhost
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an AMQP relation."""
        logger.debug("Setting up AMQP event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        import charms.rabbitmq_k8s.v0.rabbitmq as sunbeam_rabbitmq

        amqp = sunbeam_rabbitmq.RabbitMQRequires(
            self.charm, self.relation_name, self.username, self.vhost
        )
        self.framework.observe(amqp.on.ready, self._on_amqp_ready)
        self.framework.observe(amqp.on.goneaway, self._on_amqp_goneaway)
        return amqp

    def _on_amqp_ready(self, event: ops.framework.EventBase) -> None:
        """Handle AMQP change events."""
        # Ready is only emitted when the interface considers
        # that the relation is complete (indicated by a password)
        self.callback_f(event)

    def _on_amqp_goneaway(self, event: ops.framework.EventBase) -> None:
        """Handle AMQP change events."""
        # Goneaway is only emitted when the interface considers
        # that the relation is broken
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.password) and bool(
                self.interface.hostnames
            )
        except (AttributeError, KeyError):
            return False

    def context(self) -> dict:
        """Context containing AMQP connection data."""
        try:
            hosts = self.interface.hostnames
        except (AttributeError, KeyError):
            return {}
        if not hosts:
            return {}
        ctxt = super().context()
        ctxt["hostnames"] = list(set(ctxt["hostnames"]))
        ctxt["hosts"] = ",".join(ctxt["hostnames"])
        ctxt["port"] = ctxt.get("ssl_port") or self.DEFAULT_PORT
        transport_url_hosts = ",".join(
            [
                "{}:{}@{}:{}".format(
                    self.username,
                    ctxt["password"],
                    host_,  # TODO deal with IPv6
                    ctxt["port"],
                )
                for host_ in ctxt["hostnames"]
            ]
        )
        transport_url = "rabbit://{}/{}".format(
            transport_url_hosts, self.vhost
        )
        ctxt["transport_url"] = transport_url
        return ctxt


class AMQPHandler(RabbitMQHandler):
    """Backwards compatibility class for older library consumers."""

    pass


class IdentityServiceRequiresHandler(RelationHandler):
    """Handler for managing a identity-service relation."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        service_endpoints: dict,
        region: str,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.service_endpoints = service_endpoints
        self.region = region
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an Identity service relation."""
        logger.debug("Setting up Identity Service event handler")
        import charms.keystone_k8s.v1.identity_service as sun_id

        id_svc = sun_id.IdentityServiceRequires(
            self.charm, self.relation_name, self.service_endpoints, self.region
        )
        self.framework.observe(
            id_svc.on.ready, self._on_identity_service_ready
        )
        self.framework.observe(
            id_svc.on.goneaway, self._on_identity_service_goneaway
        )
        return id_svc

    def _on_identity_service_ready(
        self, event: ops.framework.EventBase
    ) -> None:
        """Handle AMQP change events."""
        # Ready is only emitted when the interface considers
        # that the relation is complete (indicated by a password)
        self.callback_f(event)

    def _on_identity_service_goneaway(
        self, event: ops.framework.EventBase
    ) -> None:
        """Handle identity service gone away event."""
        # Goneaway is only emitted when the interface considers
        # that the relation is broken or departed.
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    def update_service_endpoints(self, service_endpoints: dict) -> None:
        """Update service endpoints on the relation."""
        self.service_endpoints = service_endpoints
        self.interface.register_services(service_endpoints, self.region)

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.service_password)
        except (AttributeError, KeyError):
            return False


class BasePeerHandler(RelationHandler):
    """Base handler for managing a peers relation."""

    LEADER_READY_KEY = "leader_ready"

    def setup_event_handler(self) -> None:
        """Configure event handlers for peer relation."""
        logger.debug("Setting up peer event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        peer_int = sunbeam_interfaces.OperatorPeers(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            peer_int.on.peers_relation_joined, self._on_peers_relation_joined
        )
        self.framework.observe(
            peer_int.on.peers_data_changed, self._on_peers_data_changed
        )
        return peer_int

    def _on_peers_relation_joined(
        self, event: ops.framework.EventBase
    ) -> None:
        """Process peer joined event."""
        self.callback_f(event)

    def _on_peers_data_changed(self, event: ops.framework.EventBase) -> None:
        """Process peer data changed event."""
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether the handler is complete."""
        return bool(self.interface.peers_rel)

    def context(self) -> dict:
        """Return all app data set on the peer relation."""
        try:
            _db = {
                k.replace("-", "_"): v
                for k, v in self.interface.get_all_app_data().items()
            }
            return _db
        except (AttributeError, KeyError):
            return {}

    def set_app_data(self, settings: dict) -> None:
        """Store data in peer app db."""
        self.interface.set_app_data(settings)

    def get_app_data(self, key: str) -> Optional[str]:
        """Retrieve data from the peer relation."""
        return self.interface.get_app_data(key)

    def leader_get(self, key: str) -> str:
        """Retrieve data from the peer relation."""
        return self.peers.get_app_data(key)

    def leader_set(self, settings: dict, **kwargs) -> None:
        """Store data in peer app db."""
        settings = settings or {}
        settings.update(kwargs)
        self.set_app_data(settings)

    def set_leader_ready(self) -> None:
        """Tell peers the leader is ready."""
        self.set_app_data({self.LEADER_READY_KEY: json.dumps(True)})

    def is_leader_ready(self) -> bool:
        """Whether the leader has announced it is ready."""
        ready = self.get_app_data(self.LEADER_READY_KEY)
        if ready is None:
            return False
        else:
            return json.loads(ready)

    def set_unit_data(self, settings: Dict[str, str]) -> None:
        """Publish settings on the peer unit data bag."""
        self.interface.set_unit_data(settings)

    def get_all_unit_values(
        self, key: str, include_local_unit: bool = False
    ) -> List[str]:
        """Retrieve value for key from all related units.

        :param include_local_unit: Include value set by local unit
        """
        return self.interface.get_all_unit_values(
            key, include_local_unit=include_local_unit
        )


class CephClientHandler(RelationHandler):
    """Handler for ceph-client interface."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        allow_ec_overwrites: bool = True,
        app_name: str = None,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self.allow_ec_overwrites = allow_ec_overwrites
        self.app_name = app_name
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for an ceph-client interface."""
        logger.debug("Setting up ceph-client event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        import interface_ceph_client.ceph_client as ceph_client

        ceph = ceph_client.CephClientRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            ceph.on.pools_available, self._on_pools_available
        )
        self.framework.observe(ceph.on.broker_available, self.request_pools)
        return ceph

    def _on_pools_available(self, event: ops.framework.EventBase) -> None:
        """Handle pools available event."""
        # Ready is only emitted when the interface considers
        # that the relation is complete
        self.callback_f(event)

    def request_pools(self, event: ops.framework.EventBase) -> None:
        """Request Ceph pool creation when interface broker is ready.

        The default handler will automatically request erasure-coded
        or replicated pools depending on the configuration of the
        charm from which the handler is being used.

        To provide charm specific behaviour, subclass the default
        handler and use the required broker methods on the underlying
        interface object.
        """
        config = self.model.config.get
        data_pool_name = (
            config("rbd-pool-name")
            or config("rbd-pool")
            or self.charm.app.name
        )
        metadata_pool_name = (
            config("ec-rbd-metadata-pool") or f"{self.charm.app.name}-metadata"
        )
        weight = config("ceph-pool-weight")
        replicas = config("ceph-osd-replication-count")
        # TODO: add bluestore compression options
        if config("pool-type") == ERASURE_CODED:
            # General EC plugin config
            plugin = config("ec-profile-plugin")
            technique = config("ec-profile-technique")
            device_class = config("ec-profile-device-class")
            bdm_k = config("ec-profile-k")
            bdm_m = config("ec-profile-m")
            # LRC plugin config
            bdm_l = config("ec-profile-locality")
            crush_locality = config("ec-profile-crush-locality")
            # SHEC plugin config
            bdm_c = config("ec-profile-durability-estimator")
            # CLAY plugin config
            bdm_d = config("ec-profile-helper-chunks")
            scalar_mds = config("ec-profile-scalar-mds")
            # Profile name
            profile_name = (
                config("ec-profile-name") or f"{self.charm.app.name}-profile"
            )
            # Metadata sizing is approximately 1% of overall data weight
            # but is in effect driven by the number of rbd's rather than
            # their size - so it can be very lightweight.
            metadata_weight = weight * 0.01
            # Resize data pool weight to accommodate metadata weight
            weight = weight - metadata_weight
            # Create erasure profile
            self.interface.create_erasure_profile(
                name=profile_name,
                k=bdm_k,
                m=bdm_m,
                lrc_locality=bdm_l,
                lrc_crush_locality=crush_locality,
                shec_durability_estimator=bdm_c,
                clay_helper_chunks=bdm_d,
                clay_scalar_mds=scalar_mds,
                device_class=device_class,
                erasure_type=plugin,
                erasure_technique=technique,
            )

            # Create EC data pool
            self.interface.create_erasure_pool(
                name=data_pool_name,
                erasure_profile=profile_name,
                weight=weight,
                allow_ec_overwrites=self.allow_ec_overwrites,
                app_name=self.app_name,
            )
            # Create EC metadata pool
            self.interface.create_replicated_pool(
                name=metadata_pool_name,
                replicas=replicas,
                weight=metadata_weight,
                app_name=self.app_name,
            )
        else:
            self.interface.create_replicated_pool(
                name=data_pool_name,
                replicas=replicas,
                weight=weight,
                app_name=self.app_name,
            )

    @property
    def ready(self) -> bool:
        """Whether handler ready for use."""
        return self.interface.pools_available

    @property
    def key(self) -> str:
        """Retrieve the cephx key provided for the application."""
        return self.interface.get_relation_data().get("key")

    def context(self) -> dict:
        """Context containing Ceph connection data."""
        ctxt = super().context()
        data = self.interface.get_relation_data()
        ctxt["mon_hosts"] = ",".join(sorted(data.get("mon_hosts")))
        ctxt["auth"] = data.get("auth")
        ctxt["key"] = data.get("key")
        ctxt["rbd_features"] = None
        return ctxt


class TlsCertificatesHandler(RelationHandler):
    """Handler for certificates interface."""

    class PeerKeyStore:
        """Store private key sercret id in peer storage relation."""

        def __init__(self, relation, unit):
            self.relation = relation
            self.unit = unit

        def store_ready(self) -> bool:
            """Check if store is ready."""
            return bool(self.relation)

        def get_private_key(self) -> str:
            """Return private key."""
            try:
                key = self.relation.data[self.unit].get("private_key")
            except AttributeError:
                key = None
            return key

        def set_private_key(self, value: str):
            """Update private key."""
            self.relation.data[self.unit]["private_key"] = value

    class LocalDBKeyStore:
        """Store private key sercret id in local unit db.

        This is a fallback for when the peer relation is not
        present.
        """

        def __init__(self, state_db):
            self.state_db = state_db
            try:
                self.state_db.private_key
            except AttributeError:
                self.state_db.private_key = None

        def store_ready(self) -> bool:
            """Check if store is ready."""
            return True

        def get_private_key(self) -> str:
            """Return private key."""
            return self.state_db.private_key

        def set_private_key(self, value: str):
            """Update private key."""
            self.state_db.private_key = value

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        sans_dns: List[str] = None,
        sans_ips: List[str] = None,
        mandatory: bool = False,
    ) -> None:
        """Run constructor."""
        self._private_key = None
        self.sans_dns = sans_dns
        self.sans_ips = sans_ips
        super().__init__(charm, relation_name, callback_f, mandatory)
        try:
            self.store = self.PeerKeyStore(
                self.model.get_relation("peers"), self.charm.model.unit
            )
        except KeyError:
            self.store = self.LocalDBKeyStore(charm._state)
        self.setup_private_key()

    def setup_event_handler(self) -> None:
        """Configure event handlers for tls relation."""
        logger.debug("Setting up certificates event handler")
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        from charms.tls_certificates_interface.v1.tls_certificates import (
            TLSCertificatesRequiresV1,
        )

        self.certificates = TLSCertificatesRequiresV1(
            self.charm, "certificates"
        )
        self.framework.observe(
            self.charm.on.certificates_relation_joined,
            self._on_certificates_relation_joined,
        )
        self.framework.observe(
            self.charm.on.certificates_relation_broken,
            self._on_certificates_relation_broken,
        )
        self.framework.observe(
            self.certificates.on.certificate_available,
            self._on_certificate_available,
        )
        self.framework.observe(
            self.certificates.on.certificate_expiring,
            self._on_certificate_expiring,
        )
        self.framework.observe(
            self.certificates.on.certificate_expired,
            self._on_certificate_expired,
        )
        return self.certificates

    def setup_private_key(self) -> None:
        """Create and store private key if needed."""
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        from charms.tls_certificates_interface.v1.tls_certificates import (
            generate_private_key,
        )

        if not self.store.store_ready():
            logger.debug("Store not ready, cannot generate key")
            return

        if self.store.get_private_key():
            logger.debug("Private key already present")
            private_key_secret_id = self.store.get_private_key()
            try:
                private_key_secret = self.model.get_secret(
                    id=private_key_secret_id
                )
            except SecretNotFoundError:
                # When a unit is departing its secrets are removed by Juju.
                # So trying to access the secret will result in
                # SecretNotFoundError. Given this secret is set by this
                # unit and only consumed by this unit it is unlikely there
                # is any other reason for the secret to be missing.
                logger.debug(
                    "SecretNotFoundError not found, likely due to departing "
                    "unit."
                )
                return
            private_key_secret = self.model.get_secret(
                id=private_key_secret_id
            )
            self._private_key = (
                private_key_secret.get_content().get("private-key").encode()
            )
            return

        self._private_key = generate_private_key()
        private_key_secret = self.model.unit.add_secret(
            {"private-key": self._private_key.decode()},
            label=f"{self.charm.model.unit}-private-key",
        )

        self.store.set_private_key(private_key_secret.id)

    @property
    def private_key(self):
        """Private key for certificates."""
        logger.debug("Returning private key: {}".format(self._private_key))
        if self._private_key:
            return self._private_key.decode()
        else:
            # Private key has not been set yet
            return None

    def update_relation_data(self):
        """Request certificates outside of relation context."""
        if list(self.model.relations[self.relation_name]):
            self._request_certificates()
        else:
            logger.debug(
                "Not updating certificate request data, no relation found"
            )

    def _on_certificates_relation_joined(
        self, event: ops.framework.EventBase
    ) -> None:
        """Request certificates in response to relation join event."""
        self._request_certificates()

    def _request_certificates(self):
        """Request certificates from remote provider."""
        # Lazy import to ensure this lib is only required if the charm
        # has this relation.
        from charms.tls_certificates_interface.v1.tls_certificates import (
            generate_csr,
        )

        if self.ready:
            logger.debug("Certificate request already complete.")
            return

        if self.private_key:
            logger.debug("Private key found, requesting certificates")
        else:
            logger.debug("Cannot request certificates, private key not found")
            return

        csr = generate_csr(
            private_key=self.private_key.encode(),
            subject=self.charm.model.unit.name.replace("/", "-"),
            sans_dns=self.sans_dns,
            sans_ip=self.sans_ips,
        )
        self.certificates.request_certificate_creation(
            certificate_signing_request=csr
        )

    def _on_certificates_relation_broken(
        self, event: ops.framework.EventBase
    ) -> None:
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    def _on_certificate_available(
        self, event: ops.framework.EventBase
    ) -> None:
        self.callback_f(event)

    def _on_certificate_expiring(self, event: ops.framework.EventBase) -> None:
        logger.warning("Certificate getting expired")
        self.status.set(ActiveStatus("Certificates are getting expired soon"))

    def _on_certificate_expired(self, event: ops.framework.EventBase) -> None:
        logger.warning("Certificate expired")
        self.status.set(BlockedStatus("Certificates expired"))

    def _get_csr_from_relation_unit_data(self) -> Optional[str]:
        certificate_relations = list(self.model.relations[self.relation_name])
        if not certificate_relations:
            return None

        # unit_data format:
        # {"certificate_signing_requests": "['certificate_signing_request': 'CSRTEXT']"}
        unit_data = certificate_relations[0].data[self.charm.model.unit]
        csr = json.loads(unit_data.get("certificate_signing_requests", "[]"))
        if not csr:
            return None

        csr = csr[0].get("certificate_signing_request", None)
        return csr

    def _get_cert_from_relation_data(self, csr: str) -> dict:
        certificate_relations = list(self.model.relations[self.relation_name])
        if not certificate_relations:
            return {}

        # app data format:
        # {"certificates": "['certificate_signing_request': 'CSR',
        #                    'certificate': 'CERT', 'ca': 'CA', 'chain': 'CHAIN']"}
        certs = certificate_relations[0].data[certificate_relations[0].app]
        certs = json.loads(certs.get("certificates", "[]"))
        for certificate in certs:
            csr_from_app = certificate.get("certificate_signing_request", "")
            if csr.strip() == csr_from_app.strip():
                return {
                    "cert": certificate.get("certificate", None),
                    "ca": certificate.get("ca", None),
                    "chain": certificate.get("chain", []),
                }

        return {}

    @property
    def ready(self) -> bool:
        """Whether handler ready for use."""
        csr_from_unit = self._get_csr_from_relation_unit_data()
        if not csr_from_unit:
            return False

        certs = self._get_cert_from_relation_data(csr_from_unit)
        return True if certs else False

    def context(self) -> dict:
        """Certificates context."""
        csr_from_unit = self._get_csr_from_relation_unit_data()
        if not csr_from_unit:
            return {}

        certs = self._get_cert_from_relation_data(csr_from_unit)
        cert = certs["cert"]
        ca_cert = certs["ca"] + "\n" + "\n".join(certs["chain"])

        ctxt = {
            "key": self.private_key,
            "cert": cert,
            "ca_cert": ca_cert,
        }
        return ctxt


class IdentityCredentialsRequiresHandler(RelationHandler):
    """Handles the identity credentials relation on the requires side."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Create a new identity-credentials handler.

        Create a new IdentityCredentialsRequiresHandler that handles initial
        events from the relation and invokes the provided callbacks based on
        the event raised.

        :param charm: the Charm class the handler is for
        :type charm: ops.charm.CharmBase
        :param relation_name: the relation the handler is bound to
        :type relation_name: str
        :param callback_f: the function to call when the nodes are connected
        :type callback_f: Callable
        """
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for identity-credentials relation."""
        import charms.keystone_k8s.v0.identity_credentials as identity_credentials

        logger.debug("Setting up the identity-credentials event handler")
        credentials_service = identity_credentials.IdentityCredentialsRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            credentials_service.on.ready, self._credentials_ready
        )
        self.framework.observe(
            credentials_service.on.goneaway, self._credentials_goneaway
        )
        return credentials_service

    def _credentials_ready(self, event: ops.framework.EventBase) -> None:
        """React to credential ready event."""
        self.callback_f(event)

    def _credentials_goneaway(self, event: ops.framework.EventBase) -> None:
        """React to credential goneaway event."""
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.password)
        except (AttributeError, KeyError):
            return False


class IdentityResourceRequiresHandler(RelationHandler):
    """Handles the identity resource relation on the requires side."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ):
        """Create a new identity-ops handler.

        Create a new IdentityResourceRequiresHandler that handles initial
        events from the relation and invokes the provided callbacks based on
        the event raised.

        :param charm: the Charm class the handler is for
        :type charm: ops.charm.CharmBase
        :param relation_name: the relation the handler is bound to
        :type relation_name: str
        :param callback_f: the function to call when the nodes are connected
        :type callback_f: Callable
        :param mandatory: If the relation is mandatory to proceed with
                          configuring charm
        :type mandatory: bool
        """
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self):
        """Configure event handlers for an Identity resource relation."""
        import charms.keystone_k8s.v0.identity_resource as ops_svc

        logger.debug("Setting up Identity Resource event handler")
        ops_svc = ops_svc.IdentityResourceRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            ops_svc.on.provider_ready,
            self._on_provider_ready,
        )
        self.framework.observe(
            ops_svc.on.provider_goneaway,
            self._on_provider_goneaway,
        )
        self.framework.observe(
            ops_svc.on.response_available,
            self._on_response_available,
        )
        return ops_svc

    def _on_provider_ready(self, event) -> None:
        """Handles provider_ready  event."""
        logger.debug(
            "Identity ops provider available and ready to process any requests"
        )
        self.callback_f(event)

    def _on_provider_goneaway(self, event) -> None:
        """Handles provider_goneaway  event."""
        logger.info("Keystone provider not available process any requests")
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    def _on_response_available(self, event) -> None:
        """Handles response available  events."""
        logger.info("Handle response from identity ops")
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        return self.interface.ready()


class CeilometerServiceRequiresHandler(RelationHandler):
    """Handle ceilometer service relation on the requires side."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ):
        """Create a new ceilometer-service handler.

        Create a new CeilometerServiceRequiresHandler that handles initial
        events from the relation and invokes the provided callbacks based on
        the event raised.

        :param charm: the Charm class the handler is for
        :type charm: ops.charm.CharmBase
        :param relation_name: the relation the handler is bound to
        :type relation_name: str
        :param callback_f: the function to call when the nodes are connected
        :type callback_f: Callable
        :param mandatory: If the relation is mandatory to proceed with
                          configuring charm
        :type mandatory: bool
        """
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> None:
        """Configure event handlers for Ceilometer service relation."""
        import charms.ceilometer_k8s.v0.ceilometer_service as ceilometer_svc

        logger.debug("Setting up Ceilometer service event handler")
        svc = ceilometer_svc.CeilometerServiceRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            svc.on.config_changed,
            self._on_config_changed,
        )
        self.framework.observe(
            svc.on.goneaway,
            self._on_goneaway,
        )
        return svc

    def _on_config_changed(self, event: ops.framework.EventBase) -> None:
        """Handle config_changed  event."""
        logger.debug(
            "Ceilometer service provider config changed event received"
        )
        self.callback_f(event)

    def _on_goneaway(self, event: ops.framework.EventBase) -> None:
        """Handle gone_away  event."""
        logger.debug("Ceilometer service relation is departed/broken")
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.telemetry_secret)
        except (AttributeError, KeyError):
            return False


class CephAccessRequiresHandler(RelationHandler):
    """Handles the ceph access relation on the requires side."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool = False,
    ) -> None:
        """Create a new ceph-access handler.

        Create a new CephAccessRequiresHandler that handles initial
        events from the relation and invokes the provided callbacks based on
        the event raised.

        :param charm: the Charm class the handler is for
        :type charm: ops.charm.CharmBase
        :param relation_name: the relation the handler is bound to
        :type relation_name: str
        :param callback_f: the function to call when the nodes are connected
        :type callback_f: Callable
        """
        super().__init__(charm, relation_name, callback_f, mandatory)

    def setup_event_handler(self) -> ops.charm.Object:
        """Configure event handlers for ceph-access relation."""
        import charms.cinder_ceph_k8s.v0.ceph_access as ceph_access

        logger.debug("Setting up the ceph-access event handler")
        ceph_access = ceph_access.CephAccessRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(ceph_access.on.ready, self._ceph_access_ready)
        self.framework.observe(
            ceph_access.on.goneaway, self._ceph_access_goneaway
        )
        return ceph_access

    def _ceph_access_ready(self, event: ops.framework.EventBase) -> None:
        """React to credential ready event."""
        self.callback_f(event)

    def _ceph_access_goneaway(self, event: ops.framework.EventBase) -> None:
        """React to credential goneaway event."""
        self.callback_f(event)
        if self.mandatory:
            self.status.set(BlockedStatus("integration missing"))

    @property
    def ready(self) -> bool:
        """Whether handler is ready for use."""
        try:
            return bool(self.interface.ready)
        except (AttributeError, KeyError):
            return False

    def context(self) -> dict:
        """Context containing Ceph access data."""
        ctxt = super().context()
        data = self.interface.ceph_access_data
        ctxt["key"] = data.get("key")
        ctxt["uuid"] = data.get("uuid")
        return ctxt


ExtraOpsProcess = Callable[[ops.EventBase, dict], None]


class UserIdentityResourceRequiresHandler(RelationHandler):
    """Handle user management on IdentityResource relation."""

    CREDENTIALS_SECRET_PREFIX = "user-identity-resource-"
    CONFIGURE_SECRET_PREFIX = "configure-credential-"

    resource_identifiers: FrozenSet[str] = frozenset(
        {
            "name",
            "email",
            "description",
            "domain",
            "project",
            "project_domain",
            "enable",
            "may_exist",
        }
    )

    def __init__(
        self,
        charm: ops.CharmBase,
        relation_name: str,
        callback_f: Callable,
        mandatory: bool,
        name: str,
        domain: str,
        email: Optional[str] = None,
        description: Optional[str] = None,
        project: Optional[str] = None,
        project_domain: Optional[str] = None,
        enable: bool = True,
        may_exist: bool = True,
        role: Optional[str] = None,
        add_suffix: bool = False,
        rotate: ops.SecretRotate = ops.SecretRotate.NEVER,
        extra_ops: Optional[List[Union[dict, Callable]]] = None,
        extra_ops_process: Optional[ExtraOpsProcess] = None,
    ):
        self.username = name
        super().__init__(charm, relation_name, callback_f, mandatory)
        self.charm = charm
        self.add_suffix = add_suffix
        # add_suffix is used to add suffix to username to create unique user
        self.role = role
        self.rotate = rotate
        self.extra_ops = extra_ops
        self.extra_ops_process = extra_ops_process

        self._params = {}
        _locals = locals()
        for keys in self.resource_identifiers:
            value = _locals.get(keys)
            if value is not None:
                self._params[keys] = value

    def setup_event_handler(self) -> ops.Object:
        """Configure event handlers for the relation."""
        import charms.keystone_k8s.v0.identity_resource as id_ops

        logger.debug("Setting up Identity Resource event handler")
        ops_svc = id_ops.IdentityResourceRequires(
            self.charm,
            self.relation_name,
        )
        self.framework.observe(
            ops_svc.on.provider_ready,
            self._on_provider_ready,
        )
        self.framework.observe(
            ops_svc.on.provider_goneaway,
            self._on_provider_goneaway,
        )
        self.framework.observe(
            ops_svc.on.response_available,
            self._on_response_available,
        )
        self.framework.observe(
            self.charm.on.secret_changed, self._on_secret_changed
        )
        self.framework.observe(
            self.charm.on.secret_rotate, self._on_secret_rotate
        )
        self.framework.observe(
            self.charm.on.secret_remove, self._on_secret_remove
        )
        return ops_svc

    def _hash_ops(self, ops: list) -> str:
        """Hash ops request."""
        return hashlib.sha256(json.dumps(ops).encode()).hexdigest()

    @property
    def label(self) -> str:
        """Secret label to share over keystone resource relation."""
        return self.CREDENTIALS_SECRET_PREFIX + self.username

    @property
    def config_label(self) -> str:
        """Secret label to template configuration from."""
        return self.CONFIGURE_SECRET_PREFIX + self.username

    @property
    def _create_user_tag(self) -> str:
        return "create_user_" + self.username

    @property
    def _delete_user_tag(self) -> str:
        return "delete_user_" + self.username

    def random_string(self, length: int) -> str:
        """Utility function to generate secure random string."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for i in range(length))

    def _ensure_credentials(self, refresh_user: bool = False) -> str:
        credentials_id = self.charm.leader_get(self.label)
        suffix_length = 6
        password_length = 18

        if credentials_id:
            if refresh_user:
                username = self.username
                if self.add_suffix:
                    suffix = self.random_string(suffix_length)
                    username += "-" + suffix
                secret = self.model.get_secret(id=credentials_id)
                secret.set_content(
                    {
                        "username": username,
                        "password": self.random_string(password_length),
                    }
                )
            return credentials_id

        username = self.username
        password = self.random_string(password_length)
        if self.add_suffix:
            suffix = self.random_string(suffix_length)
            username += "-" + suffix
        secret = self.model.app.add_secret(
            {"username": username, "password": password},
            label=self.label,
            rotate=self.rotate,
        )
        self.charm.leader_set({self.label: secret.id})
        return secret.id  # type: ignore[union-attr]

    def _grant_ops_secret(self, relation: ops.Relation):
        secret = self.model.get_secret(id=self._ensure_credentials())
        secret.grant(relation)

    def _get_credentials(self) -> Tuple[str, str]:
        credentials_id = self._ensure_credentials()
        secret = self.model.get_secret(id=credentials_id)
        content = secret.get_content()
        return content["username"], content["password"]

    def get_config_credentials(self) -> Optional[Tuple[str, str]]:
        """Get credential from config secret."""
        credentials_id = self.charm.leader_get(self.config_label)
        if not credentials_id:
            return None
        secret = self.model.get_secret(id=credentials_id)
        content = secret.get_content()
        return content["username"], content["password"]

    def _update_config_credentials(self) -> bool:
        """Update config credentials.

        Returns True if credentials are updated, False otherwise.
        """
        credentials_id = self.charm.leader_get(self.config_label)
        username, password = self._get_credentials()
        content = {"username": username, "password": password}
        if credentials_id is None:
            secret = self.model.app.add_secret(
                content, label=self.config_label
            )
            self.charm.leader_set({self.config_label: secret.id})
            return True

        secret = self.model.get_secret(id=credentials_id)
        old_content = secret.get_content()
        if old_content != content:
            secret.set_content(content)
            return True
        return False

    def _create_user_request(self) -> dict:
        credentials_id = self._ensure_credentials()
        username, _ = self._get_credentials()
        requests = []
        domain = self._params["domain"]
        create_domain = {
            "name": "create_domain",
            "params": {"name": domain, "enable": True},
        }
        requests.append(create_domain)
        if self.role:
            create_role = {
                "name": "create_role",
                "params": {"name": self.role},
            }
            requests.append(create_role)
        params = self._params.copy()
        params.pop("name", None)
        create_user = {
            "name": "create_user",
            "params": {
                "name": username,
                "password": credentials_id,
                **params,
            },
        }
        requests.append(create_user)
        requests.extend(self._create_role_requests(username, domain))
        if self.extra_ops:
            for extra_op in self.extra_ops:
                if isinstance(extra_op, dict):
                    requests.append(extra_op)
                elif callable(extra_op):
                    requests.append(extra_op())
                else:
                    logger.debug(f"Invalid type of extra_op: {extra_op!r}")

        request = {
            "id": self._hash_ops(requests),
            "tag": self._create_user_tag,
            "ops": requests,
        }
        return request

    def _create_role_requests(
        self, username, domain: Optional[str]
    ) -> List[dict]:
        requests = []
        if self.role:
            params = {
                "role": self.role,
            }
            if domain:
                params["domain"] = domain
                params["user_domain"] = domain
            project_domain = self._params.get("project_domain")
            if project_domain:
                params["project_domain"] = project_domain
            params["user"] = username
            grant_role_domain = {"name": "grant_role", "params": params}
            requests.append(grant_role_domain)
            project = self._params.get("project")
            if project:
                requests.append(
                    {
                        "name": "show_project",
                        "params": {
                            "name": project,
                            "domain": project_domain or domain,
                        },
                    }
                )
                params = {
                    "project": "{{ show_project[0].id }}",
                    "role": "{{ create_role[0].id }}",
                    "user": "{{ create_user[0].id }}",
                    "user_domain": "{{ create_domain[0].id }}",
                }
                if project_domain:
                    params[
                        "project_domain"
                    ] = "{{ show_project[0].domain_id }}"
                requests.append(
                    {
                        "name": "grant_role",
                        "params": params,
                    }
                )
        return requests

    def _delete_user_request(self, users: List[str]) -> dict:
        requests = []
        for user in users:
            params = {"name": user}
            domain = self._params.get("domain")
            if domain:
                params["domain"] = domain
            requests.append(
                {
                    "name": "delete_user",
                    "params": params,
                }
            )

        return {
            "id": self._hash_ops(requests),
            "tag": self._delete_user_tag,
            "ops": requests,
        }

    def _process_create_user_response(self, response: dict) -> None:
        if {op.get("return-code") for op in response.get("ops", [])} == {0}:
            logger.debug("Create user completed.")
            config_credentials = self.get_config_credentials()
            credentials_updated = self._update_config_credentials()
            if config_credentials and credentials_updated:
                username = config_credentials[0]
                self.add_user_to_delete_user_list(username)
        else:
            logger.debug("Error in creation of user ops " f"{response}")

    def add_user_to_delete_user_list(self, user: str) -> None:
        """Update users list to delete."""
        logger.debug(f"Adding user to delete list {user}")
        old_users = self.charm.leader_get("old_users")
        delete_users = json.loads(old_users) if old_users else []
        if user not in delete_users:
            delete_users.append(user)
            self.charm.leader_set({"old_users": json.dumps(delete_users)})

    def _process_delete_user_response(self, response: dict) -> None:
        deleted_users = []
        for op in response.get("ops", []):
            if op.get("return-code") == 0:
                deleted_users.append(op.get("value").get("name"))
            else:
                logger.debug(f"Error in running delete user for op {op}")

        if deleted_users:
            logger.debug(f"Deleted users: {deleted_users}")

        old_users = self.charm.leader_get("old_users")
        users_to_delete = json.loads(old_users) if old_users else []
        new_users_to_delete = [
            x for x in users_to_delete if x not in deleted_users
        ]
        self.charm.leader_set({"old_users": json.dumps(new_users_to_delete)})

    def _on_secret_changed(self, event: ops.SecretChangedEvent):
        logger.debug(
            f"secret-changed triggered for label {event.secret.label}"
        )

        # Secret change on configured user secret
        if event.secret.label == self.config_label:
            logger.debug(
                "Calling configure charm to populate user info in "
                "configuration files"
            )
            self.callback_f(event)
        else:
            logger.debug(
                "Ignoring the secret-changed event for label "
                f"{event.secret.label}"
            )

    def _on_secret_rotate(self, event: ops.SecretRotateEvent):
        # All the juju secrets are created on leader unit, so return
        # if unit is not leader at this stage instead of checking at
        # each secret.
        logger.debug(f"secret-rotate triggered for label {event.secret.label}")
        if not self.model.unit.is_leader():
            logger.debug("Not leader unit, no action required")
            return

        # Secret rotate on stack user secret sent to ops
        if event.secret.label == self.label:
            self._ensure_credentials(refresh_user=True)
            request = self._create_user_request()
            logger.debug(f"Sending ops request: {request}")
            self.interface.request_ops(request)
        else:
            logger.debug(
                "Ignoring the secret-rotate event for label "
                f"{event.secret.label}"
            )

    def _on_secret_remove(self, event: ops.SecretRemoveEvent):
        logger.debug(f"secret-remove triggered for label {event.secret.label}")
        if not self.model.unit.is_leader():
            logger.debug("Not leader unit, no action required")
            return

        # Secret remove on configured stack admin secret
        if event.secret.label == self.config_label:
            old_users = self.charm.leader_get("old_users")
            users_to_delete = json.loads(old_users) if old_users else []

            if not users_to_delete:
                return

            request = self._delete_user_request(users_to_delete)
            logger.debug(f"Sending ops request: {request}")
            self.interface.request_ops(request)
        else:
            logger.debug(
                "Ignoring the secret-remove event for label "
                f"{event.secret.label}"
            )

    def _on_provider_ready(self, event) -> None:
        """Handles response available  events."""
        logger.info("Handle response from identity ops")
        if not self.model.unit.is_leader():
            return
        self.interface.request_ops(self._create_user_request())
        self._grant_ops_secret(event.relation)
        self.callback_f(event)

    def _on_response_available(self, event) -> None:
        """Handles response available  events."""
        if not self.model.unit.is_leader():
            return
        logger.info("Handle response from identity ops")

        response = self.interface.response
        tag = response.get("tag")
        if tag == self._create_user_tag:
            self._process_create_user_response(response)
            if self.extra_ops_process is not None:
                self.extra_ops_process(event, response)
        elif tag == self._delete_user_tag:
            self._process_delete_user_response(response)
        self.callback_f(event)

    def _on_provider_goneaway(self, event) -> None:
        """Handle gone_away  event."""
        self.callback_f(event)

    @property
    def ready(self) -> bool:
        """Whether the relation is ready."""
        return self.get_config_credentials() is not None
