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
charm classes use advanced_sunbeam_openstack.relation_handlers.RelationHandler
objects to interact with relations. These objects also provide contexts which
can be used when defining templates.

In addition to the Relation handlers the charm class can also use
advanced_sunbeam_openstack.config_contexts.ConfigContext objects which
can be used when rendering templates, these are not specific to a relation.

The charm class interacts with the containers it is managing via
advanced_sunbeam_openstack.container_handlers.PebbleHandler. The
PebbleHandler defines the pebble layers, manages pushing
configuration to the containers and managing the service running
in the container.
"""

import ipaddress
import logging
from typing import List

import ops.charm
import ops.framework
import ops.model
import ops.pebble

import advanced_sunbeam_openstack.config_contexts as sunbeam_config_contexts
import advanced_sunbeam_openstack.container_handlers as sunbeam_chandlers
import advanced_sunbeam_openstack.core as sunbeam_core
import advanced_sunbeam_openstack.relation_handlers as sunbeam_rhandlers


logger = logging.getLogger(__name__)


class OSBaseOperatorCharm(ops.charm.CharmBase):
    """Base charms for OpenStack operators."""

    _state = ops.framework.StoredState()

    def __init__(self, framework: ops.framework.Framework) -> None:
        """Run constructor."""
        super().__init__(framework)
        self._state.set_default(bootstrapped=False)
        self.relation_handlers = self.get_relation_handlers()
        self.pebble_handlers = self.get_pebble_handlers()
        self.framework.observe(self.on.config_changed, self._on_config_changed)

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
            self.amqp = sunbeam_rhandlers.AMQPHandler(
                self,
                "amqp",
                self.configure_charm,
                self.config.get("rabbit-user") or self.service_name,
                self.config.get("rabbit-vhost") or "openstack",
            )
            handlers.append(self.amqp)
        if self.can_add_handler("shared-db", handlers):
            self.db = sunbeam_rhandlers.DBHandler(
                self, "shared-db", self.configure_charm, self.databases
            )
            handlers.append(self.db)
        if self.can_add_handler("ingress", handlers):
            self.ingress = sunbeam_rhandlers.IngressHandler(
                self,
                "ingress",
                self.service_name,
                self.default_public_ingress_port,
                self.configure_charm,
            )
            handlers.append(self.ingress)
        if self.can_add_handler("peers", handlers):
            self.peers = sunbeam_rhandlers.BasePeerHandler(
                self, "peers", self.configure_charm
            )
            handlers.append(self.peers)
        if self.can_add_handler("certificates", handlers):
            self.certs = sunbeam_rhandlers.CertificatesHandler(
                self, "certificates", self.configure_charm, self.get_sans(),
            )
            handlers.append(self.certs)
        if self.can_add_handler("ovsdb-cms", handlers):
            self.certs = sunbeam_rhandlers.OVSDBCMSRequiresHandler(
                self, "ovsdb-cms", self.configure_charm,
            )
            handlers.append(self.certs)
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
                    relation_name, []):
                binding = self.model.get_binding(relation)
                ip_sans.append(binding.network.ingress_address)
                ip_sans.append(binding.network.bind_address)

        for binding_name in ['public']:
            try:
                binding = self.model.get_binding(binding_name)
                ip_sans.append(binding.network.ingress_address)
                ip_sans.append(binding.network.bind_address)
            except ops.model.ModelError:
                logging.debug(f'No binding found for {binding_name}')
        return ip_sans

    def get_domain_name_sans(self) -> List[str]:
        """Get Domain names for service."""
        domain_name_sans = []
        for binding_config in ['admin', 'internal', 'public']:
            hostname = self.config.get(f'os-{binding_config}-hostname')
            if hostname:
                domain_name_sans.append(hostname)
        return domain_name_sans

    def get_pebble_handlers(self) -> List[sunbeam_chandlers.PebbleHandler]:
        """Pebble handlers for the operator."""
        return [
            sunbeam_chandlers.PebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.configure_charm,
            )
        ]

    def get_named_pebble_handler(
        self,
        container_name: str
    ) -> sunbeam_chandlers.PebbleHandler:
        """Get pebble handler matching container_name."""
        pebble_handlers = [
            h
            for h in self.pebble_handlers
            if h.container_name == container_name
        ]
        assert len(pebble_handlers) < 2, ("Multiple pebble handlers with the "
                                          "same name found.")
        if pebble_handlers:
            return pebble_handlers[0]
        else:
            return None

    def configure_charm(self, event: ops.framework.EventBase) -> None:
        """Catchall handler to configure charm services."""
        if self.supports_peer_relation and not (
            self.unit.is_leader() or self.is_leader_ready()
        ):
            logging.debug("Leader not ready")
            return

        if not self.relation_handlers_ready():
            logging.debug("Aborting charm relations not ready")
            return

        for ph in self.pebble_handlers:
            if ph.pebble_ready:
                logging.debug(f"Running init for {ph.service_name}")
                ph.init_service(self.contexts())
            else:
                logging.debug(
                    f"Not running init for {ph.service_name},"
                    " container not ready")

        for ph in self.pebble_handlers:
            if not ph.service_ready:
                logging.debug(
                    f"Aborting container {ph.service_name} service not ready")
                return

        if not self.bootstrapped():
            self._do_bootstrap()
            if self.unit.is_leader() and self.supports_peer_relation:
                self.set_leader_ready()

        self.unit.status = ops.model.ActiveStatus()
        self._state.bootstrapped = True

    @property
    def supports_peer_relation(self) -> bool:
        """Whether the charm support the peers relation."""
        return "peers" in self.meta.relations.keys()

    @property
    def container_configs(self) -> List[sunbeam_core.ContainerConfigFile]:
        """Container configuration files for the operator."""
        return []

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
    def container_names(self) -> List[str]:
        """Names of Containers that form part of this service."""
        return [self.service_name]

    @property
    def template_dir(self) -> str:
        """Directory containing Jinja2 templates."""
        return "src/templates"

    @property
    def databases(self) -> List[str]:
        """Databases needed to support this charm.

        Defaults to a single database matching the app name.
        """
        return [self.service_name.replace("-", "_")]

    def _on_config_changed(self, event: ops.framework.EventBase) -> None:
        self.configure_charm(None)

    def containers_ready(self) -> bool:
        """Determine whether all containers are ready for configuration."""
        for ph in self.pebble_handlers:
            if not ph.service_ready:
                logger.info(f"Container incomplete: {ph.container_name}")
                return False
        return True

    def relation_handlers_ready(self) -> bool:
        """Determine whether all relations are ready for use."""
        for handler in self.relation_handlers:
            if not handler.ready:
                logger.info(f"Relation {handler.relation_name} incomplete")
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
        """Determine whether the service has been boostrapped."""
        return self._state.bootstrapped

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
        self.peers.set_leader_ready()

    def is_leader_ready(self) -> bool:
        """Has the lead unit announced that it is ready."""
        return self.peers.is_leader_ready()

    def run_db_sync(self) -> None:
        """Run DB sync to init DB.

        :raises: pebble.ExecError
        """
        if hasattr(self, 'db_sync_cmds'):
            logger.info("Syncing database...")
            container = self.unit.get_container(self.wsgi_container_name)
            for cmd in self.db_sync_cmds:
                logging.debug(f'Running sync: \n{cmd}')
                process = container.exec(cmd, timeout=5*60)
                out, warnings = process.wait_output()
                if warnings:
                    for line in warnings.splitlines():
                        logger.warning('DB Sync Out: %s', line.strip())
                logging.debug(f'Output from database sync: \n{out}')
        else:
            logger.warn(
                "Not DB sync ran. Charm does not specify self.db_sync_cmds")

    def _do_bootstrap(self) -> None:
        """Perform bootstrap."""
        try:
            self.run_db_sync()
        except ops.pebble.ExecError as e:
            logger.exception('Failed to bootstrap')
            logger.error('Exited with code %d. Stderr:', e.exit_code)
            for line in e.stderr.splitlines():
                logger.error('    %s', line)
            self._state.bootstrapped = False
            return


class OSBaseOperatorAPICharm(OSBaseOperatorCharm):
    """Base class for OpenStack API operators."""

    def __init__(self, framework: ops.framework.Framework) -> None:
        """Run constructor."""
        super().__init__(framework)
        self._state.set_default(db_ready=False)

    @property
    def service_endpoints(self) -> List[dict]:
        """List of endpoints for this service."""
        return []

    def get_relation_handlers(
        self, handlers: List[sunbeam_rhandlers.RelationHandler] = None
    ) -> List[sunbeam_rhandlers.RelationHandler]:
        """Relation handlers for the service."""
        handlers = handlers or []
        if self.can_add_handler("identity-service", handlers):
            self.id_svc = sunbeam_rhandlers.IdentityServiceRequiresHandler(
                self,
                "identity-service",
                self.configure_charm,
                self.service_endpoints,
                self.model.config["region"],
            )
            handlers.append(self.id_svc)
        handlers = super().get_relation_handlers(handlers)
        return handlers

    def service_url(self, hostname: str) -> str:
        """Service url for accessing this service via the given hostname."""
        return f"http://{hostname}:{self.default_public_ingress_port}"

    @property
    def public_url(self) -> str:
        """Url for accessing the public endpoint for this service."""
        svc_hostname = self.model.config.get(
            "os-public-hostname", self.service_name
        )
        return self.service_url(svc_hostname)

    @property
    def admin_url(self) -> str:
        """Url for accessing the admin endpoint for this service."""
        hostname = self.model.get_binding(
            "identity-service"
        ).network.ingress_address
        return self.service_url(hostname)

    @property
    def internal_url(self) -> str:
        """Url for accessing the internal endpoint for this service."""
        hostname = self.model.get_binding(
            "identity-service"
        ).network.ingress_address
        return self.service_url(hostname)

    def get_pebble_handlers(self) -> List[sunbeam_chandlers.PebbleHandler]:
        """Pebble handlers for the service."""
        return [
            sunbeam_chandlers.WSGIPebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
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
