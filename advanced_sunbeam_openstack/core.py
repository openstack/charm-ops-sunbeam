#!/usr/bin/env python3
# Copyright 2021 Billy Olsen
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import collections
import logging

import advanced_sunbeam_openstack.adapters as sunbeam_adapters
import advanced_sunbeam_openstack.templating as sunbeam_templating
import advanced_sunbeam_openstack.cprocess as sunbeam_cprocess

import charms.nginx_ingress_integrator.v0.ingress as ingress
import charms.mysql.v1.mysql as mysql

import ops.charm
import ops.framework
import ops.model

logger = logging.getLogger(__name__)


ContainerConfigFile = collections.namedtuple(
    'ContainerConfigFile',
    ['container_names', 'path', 'user', 'group'])


class PebbleHandler(ops.charm.Object):

    _state = ops.framework.StoredState()

    def __init__(self, charm, container_name, service_name,
                 container_configs, template_dir, openstack_release,
                 adapters, callback_f):
        super().__init__(charm, None)
        self._state.set_default(pebble_ready=False)
        self._state.set_default(config_pushed=False)
        self._state.set_default(service_ready=False)
        self.charm = charm
        self.container_name = container_name
        self.service_name = service_name
        self.container_configs = container_configs
        self.container_configs.extend(self.default_container_configs())
        self.template_dir = template_dir
        self.openstack_release = openstack_release
        self.adapters = adapters
        self.callback_f = callback_f
        self.setup_pebble_handler()

    def setup_pebble_handler(self):
        prefix = self.container_name.replace('-', '_')
        pebble_ready_event = getattr(
            self.charm.on,
            f'{prefix}_pebble_ready')
        self.framework.observe(pebble_ready_event,
                               self._on_service_pebble_ready)

    def _on_service_pebble_ready(self,
                                 event: ops.charm.PebbleReadyEvent) -> None:
        container = event.workload
        container.add_layer(
            self.service_name,
            self.get_layer(),
            combine=True)
        logger.debug(f'Plan: {container.get_plan()}')
        self.is_ready = True
        self.charm.configure_charm(event)
        self._state.pebble_ready = True

    def write_config(self):
        for adapter in self.adapters:
            if not adapter[1].is_ready:
                logger.info("Adapter incomplete")
                return
        container = self.charm.unit.get_container(
            self.container_name)
        if container:
            sunbeam_templating.sidecar_config_render(
                [container],
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters)
            self._state.config_pushed = True
        else:
            logger.debug(
                'Container not ready')

    def get_layer(self):
        return {}

    def init_service(self):
        self.write_config()
        self._state.service_ready = True

    def default_container_configs(self):
        return []

    @property
    def is_pebble_ready(self):
        return self._state.pebble_ready

    @property
    def is_config_pushed(self):
        return self._state.config_pushed

    @property
    def is_service_ready(self):
        return self._state.service_ready


class WSGIPebbleHandler(PebbleHandler):

    def __init__(self, charm, container_name, service_name, container_configs,
                 template_dir, openstack_release, adapters, callback_f,
                 wsgi_service_name):
        super().__init__(charm, container_name, service_name,
                         container_configs, template_dir, openstack_release,
                         adapters, callback_f)
        self.wsgi_service_name = wsgi_service_name

    def start_wsgi(self):
        container = self.charm.unit.get_container(self.container_name)
        if not container:
            logger.debug(f'{self.container_name} container is not ready. '
                         'Cannot start wgi service.')
            return
        service = container.get_service(self.wsgi_service_name)
        if service.is_running():
            container.stop(self.wsgi_service_name)

        container.start(self.wsgi_service_name)

    def get_layer(self):
        """Apache WSGI service

        :returns: pebble layer configuration for wsgi services
        :rtype: dict
        """
        return {
            'summary': f'{self.service_name} layer',
            'description': 'pebble config layer for apache wsgi',
            'services': {
                f'{self.wsgi_service_name}': {
                    'override': 'replace',
                    'summary': f'{self.service_name} wsgi',
                    'command': '/usr/sbin/apache2ctl -DFOREGROUND',
                    'startup': 'disabled',
                },
            },
        }

    def init_service(self):
        container = self.charm.unit.get_container(self.container_name)
        self.write_config()
        try:
            sunbeam_cprocess.check_output(
                container,
                f'a2ensite {self.wsgi_service_name} && sleep 1')
        except sunbeam_cprocess.ContainerProcessError:
            logger.exception(
                f'Failed to enable {self.wsgi_service_name} site in apache')
            # ignore for now - pebble is raising an exited too quickly, but it
            # appears to work properly.
        self.start_wsgi()
        self._state.service_ready = True

    @property
    def wsgi_conf(self):
        return f'/etc/apache2/sites-available/wsgi-{self.service_name}.conf'

    def default_container_configs(self):
        return [
            ContainerConfigFile(
                [self.container_name],
                self.wsgi_conf,
                'root',
                'root')]


class RelationHandler(ops.charm.Object):

    def __init__(self, charm, relation_name, callback_f):
        super().__init__(charm, None)
        self.charm = charm
        self.relation_name = relation_name
        self.callback_f = callback_f
        self.interface = self.setup_event_handler()

    def setup_event_handler(self):
        raise NotImplementedError

    def get_interface(self):
        return self.interface, self.relation_name

    @property
    def is_ready(self):
        raise NotImplementedError


class IngressHandler(RelationHandler):

    def __init__(self, charm, relation_name, service_name,
                 default_public_ingress_port, callback_f):
        self.default_public_ingress_port = default_public_ingress_port
        self.service_name = service_name
        super().__init__(charm, relation_name, callback_f)

    def setup_event_handler(self):
        logger.debug('Setting up ingress event handler')
        interface = ingress.IngressRequires(
            self.charm,
            self.ingress_config)
        return interface

    @property
    def ingress_config(self):
        # Most charms probably won't (or shouldn't) expose service-port
        # but use it if its there.
        port = self.model.config.get(
            'service-port',
            self.default_public_ingress_port)
        svc_hostname = self.model.config.get(
            'os-public-hostname',
            self.service_name)
        return {
            'service-hostname': svc_hostname,
            'service-name': self.charm.app.name,
            'service-port': port}

    @property
    def is_ready(self):
        # Nothing to wait for
        return True


class DBHandler(RelationHandler):

    def setup_event_handler(self):
        logger.debug('Setting up DB event handler')
        db = mysql.MySQLConsumer(
            self.charm,
            self.relation_name,
            {"mysql": ">=8"})
        _rname = self.relation_name.replace('-', '_')
        db_relation_event = getattr(
            self.charm.on,
            f'{_rname}_relation_changed')
        self.framework.observe(db_relation_event,
                               self._on_database_changed)
        return db

    def _on_database_changed(self, event) -> None:
        """Handles database change events."""
        databases = self.interface.databases()
        logger.info(f'Received databases: {databases}')

        if not databases:
            logger.info('Requesting a new database...')
            # The mysql-k8s operator creates a database using the relation
            # information in the form of:
            #   db_{relation_id}_{partial_uuid}_{name_suffix}
            # where name_suffix defaults to "". Specify it to the name of the
            # current app to make it somewhat understandable as to what this
            # database actually is for.
            # NOTE(wolsen): database name cannot contain a '-'
            name_suffix = self.charm.app.name.replace('-', '_')
            self.interface.new_database(name_suffix=name_suffix)
            return
        credentials = self.interface.credentials()
        # XXX Lets not log the credentials
        logger.info(f'Received credentials: {credentials}')
        self.callback_f(event)

    @property
    def is_ready(self):
        # Nothing to wait for
        return bool(self.interface.databases())


class OSBaseOperatorCharm(ops.charm.CharmBase):
    _state = ops.framework.StoredState()

    def __init__(self, framework, adapters=None):
        if adapters:
            self.adapters = adapters
        else:
            self.adapters = sunbeam_adapters.OPSRelationAdapters(self)
        super().__init__(framework)
        self.adapters.add_config_adapters(self.config_adapters)
        # Setup the observers for relationship events and pass the interfaces
        # to the adapter classes.
        self.relation_handlers = self.get_relation_handlers()
        for handler in self.relation_handlers:
            interface, relation_name = handler.get_interface()
            self.adapters.add_relation_adapter(
                interface,
                relation_name)
        self.pebble_handlers = self.get_pebble_handlers()
        self.framework.observe(self.on.config_changed,
                               self._on_config_changed)

    def get_relation_handlers(self):
        return []

    def get_pebble_handlers(self):
        return [
            PebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters,
                self.configure_charm)]

    def configure_charm(self, event):
        for h in self.pebble_handlers:
            if h.is_ready:
                h.write_config()

    @property
    def container_configs(self):
        return []

    @property
    def config_adapters(self):
        return [
            sunbeam_adapters.CharmConfigAdapter(self, 'options')]

    @property
    def handler_prefix(self):
        return self.service_name.replace('-', '_')

    @property
    def container_names(self):
        return [self.service_name]

    @property
    def template_dir(self):
        return 'src/templates'

    def _on_config_changed(self, event):
        self.configure_charm(None)

    def containers_ready(self):
        for ph in self.pebble_handlers:
            if not ph.is_service_ready:
                logger.info("Container incomplete")
                return False
        return True

    def relation_handlers_ready(self):
        for handler in self.relation_handlers:
            if not handler.is_ready:
                logger.info("Relation {} incomplete".format(handler.relation_name))
                return False
        return True


class OSBaseOperatorAPICharm(OSBaseOperatorCharm):
    _state = ops.framework.StoredState()

    def __init__(self, framework, adapters=None):
        if not adapters:
            adapters = sunbeam_adapters.APICharmAdapters(self)
        super().__init__(framework, adapters)
        self._state.set_default(db_ready=False)
        self._state.set_default(bootstrapped=False)

    def get_pebble_handlers(self):
        return [
            WSGIPebbleHandler(
                self,
                self.service_name,
                self.service_name,
                self.container_configs,
                self.template_dir,
                self.openstack_release,
                self.adapters,
                self.configure_charm,
                f'wsgi-{self.service_name}')]

    def get_relation_handlers(self):
        self.db = DBHandler(
            self,
            f'{self.service_name}-db',
            self.configure_charm)
        self.ingress = IngressHandler(
            self,
            'ingress',
            self.service_name,
            self.default_public_ingress_port,
            self.configure_charm)
        return [self.db, self.ingress]

    @property
    def container_configs(self):
        _cconfigs = super().container_configs
        _cconfigs.extend([
            ContainerConfigFile(
                [self.wsgi_container_name],
                self.service_conf,
                self.service_user,
                self.service_group)])
        return _cconfigs

    @property
    def service_user(self):
        return self.service_name

    @property
    def service_group(self):
        return self.service_name

    @property
    def service_conf(self):
        return f'/etc/{self.service_name}/{self.service_name}.conf'

    @property
    def config_adapters(self):
        _cadapters = super().config_adapters
        _cadapters.extend([
            sunbeam_adapters.WSGIWorkerConfigAdapter(self, 'wsgi_config')])
        return _cadapters

    @property
    def wsgi_container_name(self):
        return self.service_name

    @property
    def default_public_ingress_port(self):
        raise NotImplementedError

    def configure_charm(self, event):
        if not self.relation_handlers_ready():
            logging.debug("Aborting charm relations not ready")
            return

        for ph in self.pebble_handlers:
            if ph.is_pebble_ready:
                ph.init_service()

        for ph in self.pebble_handlers:
            if not ph.is_service_ready:
                logging.debug("Aborting container service not ready")
                return

        if not self.is_bootstrapped():
            self._do_bootstrap()
        self._do_bootstrap()

        self.unit.status = ops.model.ActiveStatus()
        self._state.bootstrapped = True

    def _do_bootstrap(self):
        pass

    def is_bootstrapped(self):
        """Returns True if the instance is bootstrapped.

        :returns: True if the keystone service has been bootstrapped,
                  False otherwise
        :rtype: bool
        """
        return self._state.bootstrapped
