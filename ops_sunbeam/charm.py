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

"""Base classes for defining a charm using the Operator framework.

This library provided OSBaseOperatorCharm and OSBaseOperatorAPICharm. The
charm classes use ops_sunbeam.relation_handlers.RelationHandler objects
to interact with relations. These objects also provide contexts which
can be used when defining templates.

In addition to the Relation handlers the charm class can also use
ops_sunbeam.config_contexts.ConfigContext objects which can be
used when rendering templates, these are not specific to a relation.

The charm class interacts with the containers it is managing via
ops_sunbeam.container_handlers.PebbleHandler. The PebbleHandler
defines the pebble layers, manages pushing configuration to the
containers and managing the service running in the container.
"""

import ipaddress
import logging
import urllib
from typing import (
    List,
    Mapping,
)

import ops.charm
import ops.framework
import ops.model
import ops.pebble
import ops.storage
import tenacity
from lightkube import (
    Client,
)
from lightkube.resources.core_v1 import (
    Service,
)
from ops.charm import (
    SecretChangedEvent,
    SecretRemoveEvent,
    SecretRotateEvent,
)
from ops.model import (
    ActiveStatus,
    MaintenanceStatus,
)

import ops_sunbeam.compound_status as compound_status
import ops_sunbeam.config_contexts as sunbeam_config_contexts
import ops_sunbeam.container_handlers as sunbeam_chandlers
import ops_sunbeam.core as sunbeam_core
import ops_sunbeam.guard as sunbeam_guard
import ops_sunbeam.job_ctrl as sunbeam_job_ctrl
import ops_sunbeam.relation_handlers as sunbeam_rhandlers

logger = logging.getLogger(__name__)


class OSBaseOperatorCharm(ops.charm.CharmBase):
    """Base charms for OpenStack operators."""

    _state = ops.framework.StoredState()

    # Holds set of mandatory relations
    mandatory_relations = set()

    def __init__(self, framework: ops.framework.Framework) -> None:
        """Run constructor."""
        super().__init__(framework)
        if isinstance(self.framework._storage, ops.storage.JujuStorage):
            raise ValueError(
                (
                    "use_juju_for_storage=True is deprecated and not supported "
                    "by ops_sunbeam"
                )
            )
        # unit_bootstrapped is stored in the local unit storage which is lost
        # when the pod is replaced, so this will revert to False on charm
        # upgrade or upgrade of the payload container.
        self._state.set_default(unit_bootstrapped=False)
        self.status = compound_status.Status("workload", priority=100)
        self.status_pool = compound_status.StatusPool(self)
        self.status_pool.add(self.status)
        self.relation_handlers = self.get_relation_handlers()
        self.bootstrap_status = compound_status.Status(
            "bootstrap", priority=90
        )
        self.status_pool.add(self.bootstrap_status)
        if not self.bootstrapped():
            self.bootstrap_status.set(
                MaintenanceStatus("Service not bootstrapped")
            )
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.secret_changed, self._on_secret_changed)
        self.framework.observe(self.on.secret_rotate, self._on_secret_rotate)
        self.framework.observe(self.on.secret_remove, self._on_secret_remove)

    def can_add_handler(
        self,
        relation_name: str,
        handlers: List[sunbeam_rhandlers.RelationHandler],
    ) -> bool:
        """Whether a handler for the given relation can be added."""
        if relation_name not in self.meta.relations.keys():
            logging.debug(
                f"Cannot add handler for relation {relation_name}, relation "
                "not present in charm metadata"
            )
            return False
        if relation_name in [h.relation_name for h in handlers]:
            logging.debug(
                f"Cannot add handler for relation {relation_name}, handler "
                "already present"
            )
            return False
        return True

    def get_relation_handlers(
        self, handlers: List[sunbeam_rhandlers.RelationHandler] = None
    ) -> List[sunbeam_rhandlers.RelationHandler]:
        """Relation handlers for the service."""
        handlers = handlers or []
        if self.can_add_handler("amqp", handlers):
            self.amqp = sunbeam_rhandlers.RabbitMQHandler(
                self,
                "amqp",
                self.configure_charm,
                self.config.get("rabbit-user") or self.service_name,
                self.config.get("rabbit-vhost") or "openstack",
                "amqp" in self.mandatory_relations,
            )
            handlers.append(self.amqp)
        self.dbs = {}
        for relation_name, database_name in self.databases.items():
            if self.can_add_handler(relation_name, handlers):
                db = sunbeam_rhandlers.DBHandler(
                    self,
                    relation_name,
                    self.configure_charm,
                    database_name,
                    relation_name in self.mandatory_relations,
                )
                self.dbs[relation_name] = db
                handlers.append(db)
        if self.can_add_handler("peers", handlers):
            self.peers = sunbeam_rhandlers.BasePeerHandler(
                self, "peers", self.configure_charm, False
            )
            handlers.append(self.peers)
        if self.can_add_handler("certificates", handlers):
            self.certs = sunbeam_rhandlers.TlsCertificatesHandler(
                self,
                "certificates",
                self.configure_charm,
                self.get_sans(),
                "certificates" in self.mandatory_relations,
            )
            handlers.append(self.certs)
        if self.can_add_handler("identity-credentials", handlers):
            self.ccreds = sunbeam_rhandlers.IdentityCredentialsRequiresHandler(
                self,
                "identity-credentials",
                self.configure_charm,
                "identity-credentials" in self.mandatory_relations,
            )
            handlers.append(self.ccreds)
        if self.can_add_handler("ceph-access", handlers):
            self.ceph_access = sunbeam_rhandlers.CephAccessRequiresHandler(
                self,
                "ceph-access",
                self.configure_charm,
                "ceph-access" in self.mandatory_relations,
            )
            handlers.append(self.ceph_access)
        return handlers

    def get_sans(self) -> List[str]:
        """Return Subject Alternate Names to use in cert for service."""
        str_ips_sans = [str(s) for s in self.get_ip_sans()]
        return list(set(str_ips_sans + self.get_domain_name_sans()))

    def get_ip_sans(self) -> List[ipaddress.IPv4Address]:
        """Get IP addresses for service."""
        ip_sans = []
        for relation_name in self.meta.relations.keys():
            for relation in self.framework.model.relations.get(
                relation_name, []
            ):
                binding = self.model.get_binding(relation)
                ip_sans.append(binding.network.ingress_address)
                ip_sans.append(binding.network.bind_address)

        for binding_name in ["public"]:
            try:
                binding = self.model.get_binding(binding_name)
                ip_sans.append(binding.network.ingress_address)
                ip_sans.append(binding.network.bind_address)
            except ops.model.ModelError:
                logging.debug(f"No binding found for {binding_name}")
        return ip_sans

    def get_domain_name_sans(self) -> List[str]:
        """Get Domain names for service."""
        domain_name_sans = []
        for binding_config in ["admin", "internal", "public"]:
            hostname = self.config.get(f"os-{binding_config}-hostname")
            if hostname:
                domain_name_sans.append(hostname)
        return domain_name_sans

    def check_leader_ready(self):
        """Check the leader is reporting as ready."""
        if self.supports_peer_relation and not (
            self.unit.is_leader() or self.is_leader_ready()
        ):
            raise sunbeam_guard.WaitingExceptionError("Leader not ready")

    def check_relation_handlers_ready(self):
        """Check all relation handlers are ready."""
        if not self.relation_handlers_ready():
            raise sunbeam_guard.WaitingExceptionError(
                "Not all relations are ready"
            )

    def configure_unit(self, event: ops.framework.EventBase) -> None:
        """Run configuration on this unit."""
        self.check_leader_ready()
        self.check_relation_handlers_ready()
        self._state.unit_bootstrapped = True

    def configure_app_leader(self, event):
        """Run global app setup.

        These are tasks that should only be run once per application and only
        the leader runs them.
        """
        self.set_leader_ready()

    def configure_app_non_leader(self, event):
        """Setup steps for a non-leader after leader has bootstrapped."""
        if not self.bootstrapped:
            raise sunbeam_guard.WaitingExceptionError("Leader not ready")

    def configure_app(self, event):
        """Check on (and run if leader) app wide tasks."""
        if self.unit.is_leader():
            self.configure_app_leader(event)
        else:
            self.configure_app_non_leader(event)

    def post_config_setup(self):
        """Configuration steps after services have been setup."""
        logger.info("Setting active status")
        self.status.set(ActiveStatus(""))

    def configure_charm(self, event: ops.framework.EventBase) -> None:
        """Catchall handler to configure charm services."""
        with sunbeam_guard.guard(self, "Bootstrapping"):
            self.configure_unit(event)
            self.configure_app(event)
            self.bootstrap_status.set(ActiveStatus())
            self.post_config_setup()

    @property
    def supports_peer_relation(self) -> bool:
        """Whether the charm support the peers relation."""
        return "peers" in self.meta.relations.keys()

    @property
    def config_contexts(
        self,
    ) -> List[sunbeam_config_contexts.CharmConfigContext]:
        """Return the configuration adapters for the operator."""
        return [sunbeam_config_contexts.CharmConfigContext(self, "options")]

    @property
    def _unused_handler_prefix(self) -> str:
        """Prefix for handlers."""
        return self.service_name.replace("-", "_")

    @property
    def template_dir(self) -> str:
        """Directory containing Jinja2 templates."""
        return "src/templates"

    @property
    def databases(self) -> Mapping[str, str]:
        """Return a mapping of database relation names to database names.

        Use this to define the databases required by an application.

        All entries here
        that have a corresponding relation defined in metadata
        will automatically have a a DBHandler instance set up for it,
        and assigned to `charm.dbs[relation_name]`.
        Entries that don't have a matching relation in metadata
        will be ignored.
        Note that the relation interface type is expected to be 'mysql_client'.

        It defaults to loading a relation named "database",
        with the database named after the service name.
        """
        return {"database": self.service_name.replace("-", "_")}

    def _on_config_changed(self, event: ops.framework.EventBase) -> None:
        self.configure_charm(event)

    def _on_secret_changed(self, event: SecretChangedEvent) -> None:
        # By default read the latest content of secret
        # this will allow juju to trigger secret-remove
        # event for old revision
        event.secret.get_content(refresh=True)
        self.configure_charm(event)

    def _on_secret_rotate(self, event: SecretRotateEvent) -> None:
        # Placeholder to handle secret rotate event
        # charms should handle the event if required
        pass

    def _on_secret_remove(self, event: SecretRemoveEvent) -> None:
        # Placeholder to handle secret remove event
        # charms should handle the event if required
        pass

    def relation_handlers_ready(self) -> bool:
        """Determine whether all relations are ready for use."""
        ready_relations = {
            handler.relation_name
            for handler in self.relation_handlers
            if handler.mandatory and handler.ready
        }
        not_ready_relations = self.mandatory_relations.difference(
            ready_relations
        )

        if len(not_ready_relations) != 0:
            logger.info(f"Relations {not_ready_relations} incomplete")
            return False

        return True

    def contexts(self) -> sunbeam_core.OPSCharmContexts:
        """Construct context for rendering templates."""
        ra = sunbeam_core.OPSCharmContexts(self)
        for handler in self.relation_handlers:
            if handler.relation_name not in self.meta.relations.keys():
                logger.info(
                    f"Dropping handler for relation {handler.relation_name}, "
                    "relation not present in charm metadata"
                )
                continue
            if handler.ready:
                ra.add_relation_handler(handler)
        ra.add_config_contexts(self.config_contexts)
        return ra

    def bootstrapped(self) -> bool:
        """Determine whether the service has been bootstrapped."""
        return self._state.unit_bootstrapped and self.is_leader_ready()

    def leader_set(self, settings: dict = None, **kwargs) -> None:
        """Juju set data in peer data bag."""
        settings = settings or {}
        settings.update(kwargs)
        self.peers.set_app_data(settings=settings)

    def leader_get(self, key: str) -> str:
        """Retrieve data from the peer relation."""
        return self.peers.get_app_data(key)

    def set_leader_ready(self) -> None:
        """Tell peers that the leader is ready."""
        try:
            self.peers.set_leader_ready()
        except AttributeError:
            logging.warning("Cannot set leader ready as peer relation missing")

    def is_leader_ready(self) -> bool:
        """Has the lead unit announced that it is ready."""
        leader_ready = False
        try:
            leader_ready = self.peers.is_leader_ready()
        except AttributeError:
            logging.warning(
                "Cannot check leader ready as peer relation missing. "
                "Assuming it is ready."
            )
            leader_ready = True
        return leader_ready


class OSBaseOperatorCharmK8S(OSBaseOperatorCharm):
    """Base charm class for k8s based charms."""

    def __init__(self, framework: ops.framework.Framework) -> None:
        """Run constructor."""
        super().__init__(framework)
        self.pebble_handlers = self.get_pebble_handlers()

    def get_pebble_handlers(self) -> List[sunbeam_chandlers.PebbleHandler]:
        """Pebble handlers for the operator."""
        return [
            sunbeam_chandlers.PebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.configure_charm,
            )
        ]

    def get_named_pebble_handler(
        self, container_name: str
    ) -> sunbeam_chandlers.PebbleHandler:
        """Get pebble handler matching container_name."""
        pebble_handlers = [
            h
            for h in self.pebble_handlers
            if h.container_name == container_name
        ]
        assert len(pebble_handlers) < 2, (
            "Multiple pebble handlers with the " "same name found."
        )
        if pebble_handlers:
            return pebble_handlers[0]
        else:
            return None

    def get_named_pebble_handlers(
        self, container_names: List[str]
    ) -> List[sunbeam_chandlers.PebbleHandler]:
        """Get pebble handlers matching container_names."""
        return [
            h
            for h in self.pebble_handlers
            if h.container_name in container_names
        ]

    def init_container_services(self):
        """Run init on pebble handlers that are ready."""
        for ph in self.pebble_handlers:
            if ph.pebble_ready:
                logging.debug(f"Running init for {ph.service_name}")
                ph.init_service(self.contexts())
            else:
                logging.debug(
                    f"Not running init for {ph.service_name},"
                    " container not ready"
                )
                raise sunbeam_guard.WaitingExceptionError(
                    "Payload container not ready"
                )

    def check_pebble_handlers_ready(self):
        """Check pebble handlers are ready."""
        for ph in self.pebble_handlers:
            if not ph.service_ready:
                logging.debug(
                    f"Aborting container {ph.service_name} service not ready"
                )
                raise sunbeam_guard.WaitingExceptionError(
                    "Container service not ready"
                )

    def configure_unit(self, event: ops.framework.EventBase) -> None:
        """Run configuration on this unit."""
        self.check_leader_ready()
        self.check_relation_handlers_ready()
        self.open_ports()
        self.init_container_services()
        self.check_pebble_handlers_ready()
        self.run_db_sync()
        self._state.unit_bootstrapped = True

    def add_pebble_health_checks(self):
        """Add health checks for services in payload containers."""
        for ph in self.pebble_handlers:
            ph.add_healthchecks()

    def post_config_setup(self):
        """Configuration steps after services have been setup."""
        self.add_pebble_health_checks()
        logger.info("Setting active status")
        self.status.set(ActiveStatus(""))

    @property
    def container_configs(self) -> List[sunbeam_core.ContainerConfigFile]:
        """Container configuration files for the operator."""
        return []

    @property
    def container_names(self) -> List[str]:
        """Names of Containers that form part of this service."""
        return [self.service_name]

    def containers_ready(self) -> bool:
        """Determine whether all containers are ready for configuration."""
        for ph in self.pebble_handlers:
            if not ph.service_ready:
                logger.info(f"Container incomplete: {ph.container_name}")
                return False
        return True

    @property
    def db_sync_container_name(self) -> str:
        """Name of Containerto run db sync from."""
        return self.service_name

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        retry=(
            tenacity.retry_if_exception_type(ops.pebble.ChangeError)
            | tenacity.retry_if_exception_type(ops.pebble.ExecError)
        ),
        after=tenacity.after_log(logger, logging.WARNING),
        wait=tenacity.wait_exponential(multiplier=1, min=10, max=300),
    )
    def _retry_db_sync(self, cmd):
        container = self.unit.get_container(self.db_sync_container_name)
        logging.debug("Running sync: \n%s", cmd)
        process = container.exec(cmd, timeout=5 * 60)
        out, warnings = process.wait_output()
        if warnings:
            for line in warnings.splitlines():
                logger.warning("DB Sync Out: %s", line.strip())
                logging.debug("Output from database sync: \n%s", out)

    @sunbeam_job_ctrl.run_once_per_unit("db-sync")
    def run_db_sync(self) -> None:
        """Run DB sync to init DB.

        :raises: pebble.ExecError
        """
        if not self.unit.is_leader():
            logging.info("Not lead unit, skipping DB syncs")
            return
        try:
            if self.db_sync_cmds:
                logger.info("Syncing database...")
                for cmd in self.db_sync_cmds:
                    try:
                        self._retry_db_sync(cmd)
                    except tenacity.RetryError:
                        raise sunbeam_guard.BlockedExceptionError(
                            "DB sync failed"
                        )
        except AttributeError:
            logger.warning(
                "Not DB sync ran. Charm does not specify self.db_sync_cmds"
            )

    def open_ports(self):
        """Register ports in underlying cloud."""
        pass


class OSBaseOperatorAPICharm(OSBaseOperatorCharmK8S):
    """Base class for OpenStack API operators."""

    mandatory_relations = {"database", "identity-service", "ingress-public"}

    def __init__(self, framework: ops.framework.Framework) -> None:
        """Run constructor."""
        super().__init__(framework)

    @property
    def service_endpoints(self) -> List[dict]:
        """List of endpoints for this service."""
        return []

    def get_relation_handlers(
        self, handlers: List[sunbeam_rhandlers.RelationHandler] = None
    ) -> List[sunbeam_rhandlers.RelationHandler]:
        """Relation handlers for the service."""
        handlers = handlers or []
        # Note: intentionally including the ingress handler here in order to
        # be able to link the ingress and identity-service handlers.
        if self.can_add_handler("ingress-internal", handlers):
            self.ingress_internal = sunbeam_rhandlers.IngressInternalHandler(
                self,
                "ingress-internal",
                self.service_name,
                self.default_public_ingress_port,
                self._ingress_changed,
                "ingress-internal" in self.mandatory_relations,
            )
            handlers.append(self.ingress_internal)
        if self.can_add_handler("ingress-public", handlers):
            self.ingress_public = sunbeam_rhandlers.IngressPublicHandler(
                self,
                "ingress-public",
                self.service_name,
                self.default_public_ingress_port,
                self._ingress_changed,
                "ingress-public" in self.mandatory_relations,
            )
            handlers.append(self.ingress_public)
        if self.can_add_handler("identity-service", handlers):
            self.id_svc = sunbeam_rhandlers.IdentityServiceRequiresHandler(
                self,
                "identity-service",
                self.configure_charm,
                self.service_endpoints,
                self.model.config["region"],
                "identity-service" in self.mandatory_relations,
            )
            handlers.append(self.id_svc)
        return super().get_relation_handlers(handlers)

    def _ingress_changed(self, event: ops.framework.EventBase) -> None:
        """Ingress changed callback.

        Invoked when the data on the ingress relation has changed. This will
        update the relevant endpoints with the identity service, and then
        call the configure_charm.
        """
        logger.debug("Received an ingress_changed event")
        try:
            if self.id_svc.update_service_endpoints:
                logger.debug(
                    "Updating service endpoints after ingress "
                    "relation changed."
                )
                self.id_svc.update_service_endpoints(self.service_endpoints)
        except (AttributeError, KeyError):
            pass

        self.configure_charm(event)

    def service_url(self, hostname: str) -> str:
        """Service url for accessing this service via the given hostname."""
        return f"http://{hostname}:{self.default_public_ingress_port}"

    @property
    def public_ingress_address(self) -> str:
        """IP address or hostname for access to this service."""
        svc_hostname = self.model.config.get("os-public-hostname")
        if svc_hostname:
            return svc_hostname

        client = Client()
        charm_service = client.get(
            Service, name=self.app.name, namespace=self.model.name
        )

        status = charm_service.status
        if status:
            load_balancer_status = status.loadBalancer
            if load_balancer_status:
                ingress_addresses = load_balancer_status.ingress
                if ingress_addresses:
                    logger.debug(
                        "Found ingress addresses on loadbalancer " "status"
                    )
                    ingress_address = ingress_addresses[0]
                    addr = ingress_address.hostname or ingress_address.ip
                    if addr:
                        logger.debug(
                            "Using ingress address from loadbalancer "
                            f"as {addr}"
                        )
                        return ingress_address.hostname or ingress_address.ip

        hostname = self.model.get_binding(
            "identity-service"
        ).network.ingress_address
        return hostname

    @property
    def public_url(self) -> str:
        """Url for accessing the public endpoint for this service."""
        try:
            if self.ingress_public.url:
                logger.debug(
                    "Ingress-public relation found, returning "
                    "ingress-public.url of: %s",
                    self.ingress_public.url,
                )
                return self.add_explicit_port(self.ingress_public.url)
        except (AttributeError, KeyError):
            pass

        return self.add_explicit_port(
            self.service_url(self.public_ingress_address)
        )

    @property
    def admin_url(self) -> str:
        """Url for accessing the admin endpoint for this service."""
        hostname = self.model.get_binding(
            "identity-service"
        ).network.ingress_address
        return self.add_explicit_port(self.service_url(hostname))

    @property
    def internal_url(self) -> str:
        """Url for accessing the internal endpoint for this service."""
        try:
            if self.ingress_internal.url:
                logger.debug(
                    "Ingress-internal relation found, returning "
                    "ingress_internal.url of: %s",
                    self.ingress_internal.url,
                )
                return self.add_explicit_port(self.ingress_internal.url)
        except (AttributeError, KeyError):
            pass

        hostname = self.model.get_binding(
            "identity-service"
        ).network.ingress_address
        return self.add_explicit_port(self.service_url(hostname))

    def get_pebble_handlers(self) -> List[sunbeam_chandlers.PebbleHandler]:
        """Pebble handlers for the service."""
        return [
            sunbeam_chandlers.WSGIPebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.configure_charm,
                f"wsgi-{self.service_name}",
            )
        ]

    @property
    def container_configs(self) -> List[sunbeam_core.ContainerConfigFile]:
        """Container configuration files for the service."""
        _cconfigs = super().container_configs
        _cconfigs.extend(
            [
                sunbeam_core.ContainerConfigFile(
                    self.service_conf,
                    self.service_user,
                    self.service_group,
                )
            ]
        )
        return _cconfigs

    @property
    def service_user(self) -> str:
        """Service user file and directory ownership."""
        return self.service_name

    @property
    def service_group(self) -> str:
        """Service group file and directory ownership."""
        return self.service_name

    @property
    def service_conf(self) -> str:
        """Service default configuration file."""
        return f"/etc/{self.service_name}/{self.service_name}.conf"

    @property
    def config_contexts(self) -> List[sunbeam_config_contexts.ConfigContext]:
        """Generate list of configuration adapters for the charm."""
        _cadapters = super().config_contexts
        _cadapters.extend(
            [
                sunbeam_config_contexts.WSGIWorkerConfigContext(
                    self, "wsgi_config"
                )
            ]
        )
        return _cadapters

    @property
    def wsgi_container_name(self) -> str:
        """Name of the WSGI application container."""
        return self.service_name

    @property
    def default_public_ingress_port(self) -> int:
        """Port to use for ingress access to service."""
        raise NotImplementedError

    @property
    def db_sync_container_name(self) -> str:
        """Name of Containerto run db sync from."""
        return self.wsgi_container_name

    @property
    def healthcheck_period(self) -> str:
        """Healthcheck period for the service."""
        return "10s"  # Default value in pebble

    @property
    def healthcheck_http_url(self) -> str:
        """Healthcheck HTTP URL for the service."""
        return f"http://localhost:{self.default_public_ingress_port}/"

    @property
    def healthcheck_http_timeout(self) -> str:
        """Healthcheck HTTP timeout for the service."""
        return "3s"

    def open_ports(self):
        """Register ports in underlying cloud."""
        self.unit.open_port("tcp", self.default_public_ingress_port)

    def add_explicit_port(self, org_url: str) -> str:
        """Update a url to add an explicit port.

        Keystone auth endpoint parsing can give odd results if
        an explicit port is missing.
        """
        url = urllib.parse.urlparse(org_url)
        new_netloc = url.netloc
        if not url.port:
            if url.scheme == "http":
                new_netloc = url.netloc + ":80"
            elif url.scheme == "https":
                new_netloc = url.netloc + ":443"
        return urllib.parse.urlunparse(
            (
                url.scheme,
                new_netloc,
                url.path,
                url.params,
                url.query,
                url.fragment,
            )
        )
