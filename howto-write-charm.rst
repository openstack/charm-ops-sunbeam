=============
New API Charm
=============

The example below will walk through the creation of a basic API charm for the
OpenStack `Glance <https://wiki.openstack.org/wiki/Glance>`__ service designed
to run on kubernetes.

Create the skeleton charm
=========================

Prerequisite
~~~~~~~~~~~~

The charmcraft tool builds a skeleton charm.

.. code:: bash

   mkdir charm-glance-operator
   cd charm-glance-operator/
   charmcraft init --name sunbeam-glance-operator

Some useful files can be found in ASO so that needs
to be available locally

.. code:: bash

    git clone https://github.com/openstack-charmers/advanced-sunbeam-openstack

Amend charmcraft file to include git at build time:

.. code:: bash

    parts:
      charm:
        build-packages:
          - git

Add Metadata
============

The first job is to write the metadata yaml.

.. code:: yaml

   # Copyright 2021 Canonical Ltd
   # See LICENSE file for licensing details.
   name: sunbeam-glance-operator
   maintainer: OpenStack Charmers <openstack-charmers@lists.ubuntu.com>
   summary: OpenStack Image Registry and Delivery Service
   description: |
     The Glance project provides an image registration and discovery service
     and an image delivery service. These services are used in conjunction
     by Nova to deliver images.
   version: 3
   bases:
     - name: ubuntu
       channel: 20.04/stable
   tags:
     - openstack
     - storage
     - misc

   containers:
     glance-api:
       resource: glance-api-image

   resources:
     glance-api-image:
       type: oci-image
       description: OCI image for OpenStack Glance (kolla/glance-api-image)

   requires:
     shared-db:
       interface: mysql_datastore
       limit: 1
     ingress:
       interface: ingress
     identity-service:
       interface: keystone
       limit: 1
     amqp:
       interface: rabbitmq
     image-service:
       interface: glance
     ceph:
       interface: ceph-client

   peers:
     peers:
       interface: glance-peer

The first part of the metadata is pretty self explanatory, is sets out the some
general information about the charm. The `containers` section lists all the
containers that this charm will manage. Glance consists of just one container
so just one container is listed here. Similarly in the resources section all
the container images are listed. Since there is just one container only one
image is listed here.

The requires section lists all the relations this charm is reliant on. These
are all standard for an OpenStack API charm plus the additional ceph relation.

Common Files
============

ASO contains some common files which need to copied into the charm.

.. code:: bash

    cp advanced-sunbeam-openstack/shared_code/tox.ini charm-glance-operator/
    cp advanced-sunbeam-openstack/shared_code/requirements.txt charm-glance-operator/
    cp -r advanced-sunbeam-openstack/shared_code/templates charm-glance-operator/src/
    cp advanced-sunbeam-openstack/shared_code/.stestr.conf charm-glance-operator/
    cp advanced-sunbeam-openstack/shared_code/test-requirements.txt charm-glance-operator/

At the moment the wsgi template needs to be renamed to add incluse the
service name.

.. code:: bash

    cd charm-glance-operator
    mv /src/templates/wsgi-template.conf.j2 ./src/templates/wsgi-glance-api.conf.j2

There are some config options which are common accross the OpenStack api charms. Since
this charm uses ceph add the ceph config options too.

.. code:: bash

    cd advanced-sunbeam-openstack/shared_code/
    echo "options:" > ../../charm-glance-operator/config.yaml
    cat config-api.yaml >> ../../charm-glance-operator/config.yaml
    cat config-ceph-options.yaml >> ../../charm-glance-operator/config.yaml

Fetch interface libs corresponding to the requires interfaces:

.. code:: bash

    cd charm-glance-operator
    charmcraft fetch-lib charms.nginx_ingress_integrator.v0.ingress
    charmcraft fetch-lib charms.sunbeam_mysql_k8s.v0.mysql
    charmcraft fetch-lib charms.sunbeam_keystone_operator.v0.identity_service
    charmcraft fetch-lib charms.sunbeam_rabbitmq_operator.v0.amqp
    charmcraft fetch-lib charms.observability_libs.v0.kubernetes_service_patch

Templates
=========

Much of the glance configuration is covered by common templates which were copied
into the charm in the previous step. The only additional template for this charm
is for `glance-api.conf`. Add the following into `./src/templates/glance-api.conf.j2`

.. code::

    ###############################################################################
    # [ WARNING ]
    # glance configuration file maintained by Juju
    # local changes may be overwritten.
    ###############################################################################
    [DEFAULT]
    debug = {{ options.debug }}
    transport_url = {{ amqp.transport_url }}

    {% include "parts/section-database" %}

    {% include "parts/section-identity" %}



    [glance_store]
    default_backend = ceph
    filesystem_store_datadir = /var/lib/glance/images/

    [ceph]
    rbd_store_chunk_size = 8
    rbd_store_pool = glance
    rbd_store_user = glance
    rados_connect_timeout = 0
    rbd_store_ceph_conf = /etc/ceph/ceph.conf

    [paste_deploy]
    flavor = keystone

Charm
=====

This is subject to change as more of the common code is generalised into aso.

Inherit from OSBaseOperatorAPICharm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Start by creating a charm class that inherits from the `OSBaseOperatorAPICharm`
class which contains all the code which is common accross OpenStack API charms.

.. code:: python

    #!/usr/bin/env python3
    """Glance Operator Charm.

    This charm provide Glance services as part of an OpenStack deployment
    """

    import logging
    from typing import List

    from ops.framework import StoredState
    from ops.main import main

    import advanced_sunbeam_openstack.cprocess as sunbeam_cprocess
    import advanced_sunbeam_openstack.charm as sunbeam_charm
    import advanced_sunbeam_openstack.core as sunbeam_core
    import advanced_sunbeam_openstack.relation_handlers as sunbeam_rhandlers
    import advanced_sunbeam_openstack.config_contexts as sunbeam_ctxts

    from charms.observability_libs.v0.kubernetes_service_patch \
        import KubernetesServicePatch

    logger = logging.getLogger(__name__)


    class GlanceOperatorCharm(sunbeam_charm.OSBaseOperatorAPICharm):
        """Charm the service."""

        ceph_conf = "/etc/ceph/ceph.conf"

        _state = StoredState()
        service_name = "glance-api"
        wsgi_admin_script = '/usr/bin/glance-wsgi-api'
        wsgi_public_script = '/usr/bin/glance-wsgi-api'

        def __init__(self, framework):
            super().__init__(framework)
            self.service_patcher = KubernetesServicePatch(
                self,
                [
                    ('public', self.default_public_ingress_port),
                ]
            )

The `KubernetesServicePatch` module is used to expose the service within kubernetes
so that it is externally visable. Hopefully this will eventually be accomplished by
Juju and and can be removed.

Ceph Support
~~~~~~~~~~~~

This glance charm with relate to Ceph to store uploaded images. A relation to Ceph
is not common accross the api charms to we need to add the components from ASO to
support the ceph relation.


.. code:: python

    @property
    def config_contexts(self) -> List[sunbeam_ctxts.ConfigContext]:
        """Configuration contexts for the operator."""
        contexts = super().config_contexts
        contexts.append(
            sunbeam_ctxts.CephConfigurationContext(self, "ceph_config"))
        return contexts

    @property
    def container_configs(self) -> List[sunbeam_core.ContainerConfigFile]:
        """Container configurations for the operator."""
        _cconfigs = super().container_configs
        _cconfigs.extend(
            [
                sunbeam_core.ContainerConfigFile(
                    [self.service_name],
                    self.ceph_conf,
                    self.service_user,
                    self.service_group,
                ),
            ]
        )
        return _cconfigs

    def get_relation_handlers(self) -> List[sunbeam_rhandlers.RelationHandler]:
        """Relation handlers for the service."""
        handlers = super().get_relation_handlers()
        self.ceph = sunbeam_rhandlers.CephClientHandler(
            self,
            "ceph",
            self.configure_charm,
            allow_ec_overwrites=True,
            app_name='rbd'
        )


In the `config_contexts` `sunbeam_ctxts.CephConfigurationContext` is added to the list
of config contexts. This will look after transalting some of the charms
configuration options into Ceph configuration.

In `container_configs` the `ceph.conf` is added to the list of configuration
files to be rendered in containers.

Finally in `get_relation_handlers` the relation handler for the `ceph` relation is
added.

OpenStack Endpoints
~~~~~~~~~~~~~~~~~~~

`OSBaseOperatorAPICharm` makes assumptions based on the self.service_name but a few
of these are broken as there is a mix between `glance` and `glance_api`. Finally the
charm needs to specify what endpoint should be registered in the keystone catalgue
each charm needs to explicitly state this as there is a lot of variation between
services

.. code:: python

    @property
    def service_conf(self) -> str:
        """Service default configuration file."""
        return f"/etc/glance/glance-api.conf"

    @property
    def service_user(self) -> str:
        """Service user file and directory ownership."""
        return 'glance'

    @property
    def service_group(self) -> str:
        """Service group file and directory ownership."""
        return 'glance'

    @property
    def service_endpoints(self):
        return [
            {
                'service_name': 'glance',
                'type': 'image',
                'description': "OpenStack Image",
                'internal_url': f'{self.internal_url}',
                'public_url': f'{self.public_url}',
                'admin_url': f'{self.admin_url}'}]

    @property
        return 9292

Bootstrap
~~~~~~~~~

Currently ASO does not support database migrations, this will be fixed soon but until
then add a db sync to the bootstrap process.

.. code:: python

    def _do_bootstrap(self):
        """
        Starts the appropriate services in the order they are needed.
        If the service has not yet been bootstrapped, then this will
         1. Create the database
        """
        super()._do_bootstrap()
        try:
            container = self.unit.get_container(self.wsgi_container_name)
            logger.info("Syncing database...")
            out = sunbeam_cprocess.check_output(
                container,
                [
                    'sudo', '-u', 'glance',
                    'glance-manage', '--config-dir',
                    '/etc/glance', 'db', 'sync'],
                service_name='keystone-db-sync',
                timeout=180)
            logging.debug(f'Output from database sync: \n{out}')
        except sunbeam_cprocess.ContainerProcessError:
            logger.exception('Failed to bootstrap')
            self._state.bootstrapped = False
            return

Configure Charm
~~~~~~~~~~~~~~~

The container used by this charm should include `ceph-common` but it currently does
not. To work around this install it in the container. As glance communicates with Ceph
another specialisation is needed to run `ceph-authtool`.


.. code:: python

    def configure_charm(self, event) -> None:
        """Catchall handler to cconfigure charm services."""
        if not self.relation_handlers_ready():
            logging.debug("Defering configuration, charm relations not ready")
            return

        for ph in self.pebble_handlers:
            if ph.pebble_ready:
                container = self.unit.get_container(
                    ph.container_name
                )
                sunbeam_cprocess.check_call(
                    container,
                    ['apt', 'update'])
                sunbeam_cprocess.check_call(
                    container,
                    ['apt', 'install', '-y', 'ceph-common'])
                try:
                    sunbeam_cprocess.check_call(
                        container,
                        ['ceph-authtool',
                         f'/etc/ceph/ceph.client.{self.app.name}.keyring',
                         '--create-keyring',
                         f'--name=client.{self.app.name}',
                         f'--add-key={self.ceph.key}']
                    )
                except sunbeam_cprocess.ContainerProcessError:
                    pass
                ph.init_service(self.contexts())

        super().configure_charm(event)
        # Restarting services after bootstrap should be in aso
        if self._state.bootstrapped:
            for handler in self.pebble_handlers:
                handler.start_service()

OpenStack Release
~~~~~~~~~~~~~~~~~

This charm is spefic to a particular release so the final step is to add a
release specific class.

.. code:: python

    class GlanceWallabyOperatorCharm(GlanceOperatorCharm):

        openstack_release = 'wallaby'

    if __name__ == "__main__":
        # Note: use_juju_for_storage=True required per
        # https://github.com/canonical/operator/issues/506
        main(GlanceWallabyOperatorCharm, use_juju_for_storage=True)
