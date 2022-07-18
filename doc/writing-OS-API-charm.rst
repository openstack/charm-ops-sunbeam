=============
New API Charm
=============

The example below will walk through the creation of a basic API charm for the
OpenStack `Ironic <https://wiki.openstack.org/wiki/Ironic>`__ service designed
to run on kubernetes.

Create the skeleton charm
=========================

Prerequisite
~~~~~~~~~~~~

Build a base geneeric charm with the `charmcraft` tool.

.. code:: bash

   mkdir charm-ironic-operator
   cd charm-ironic-operator
   charmcraft init --name sunbeam-ironic-operator

Add ASO common files to new charm. The script will ask a few basic questions:

.. code:: bash

    git clone https://github.com/openstack-charmers/advanced-sunbeam-openstack
    cd advanced-sunbeam-openstack
    ./sunbeam-charm-init.sh ~/branches/charm-ironic-operator

    This tool is designed to be used after 'charmcraft init' was initially run
    service_name [ironic]: ironic
    charm_name [sunbeam-ironic-operator]: sunbeam-ironic-operator
    ingress_port []: 6385
    db_sync_command [] ironic-dbsync --config-file /etc/ironic/ironic.conf create_schema: 

Fetch interface libs corresponding to the requires interfaces:

.. code:: bash

    cd charm-ironic-operator
    charmcraft login
    charmcraft fetch-lib charms.nginx_ingress_integrator.v0.ingress
    charmcraft fetch-lib charms.sunbeam_mysql_k8s.v0.mysql
    charmcraft fetch-lib charms.sunbeam_keystone_operator.v0.identity_service
    charmcraft fetch-lib charms.sunbeam_rabbitmq_operator.v0.amqp
    charmcraft fetch-lib charms.observability_libs.v0.kubernetes_service_patch

Templates
=========

Much of the service configuration is covered by common templates which were copied
into the charm in the previous step. The only additional template for this charm
is for `ironic.conf`. Add the following into `./src/templates/ironic.conf.j2`

.. code::

    [DEFAULT]
    debug = {{ options.debug }}
    auth_strategy=keystone
    transport_url = {{ amqp.transport_url }}

    [keystone_authtoken]
    {% include "parts/identity-data" %}

    [database]
    {% include "parts/database-connection" %}

    [neutron]
    {% include "parts/identity-data" %}

    [glance]
    {% include "parts/identity-data" %}

    [cinder]
    {% include "parts/identity-data" %}

    [service_catalog]
    {% include "parts/identity-data" %}


Make charm deployable
=====================

The next step is to pack the charm into a deployable format

.. code:: bash

    cd charm-ironic-operator
    charmcraft pack


Deploy Charm
============

The charm can now be deployed. The Kolla project has images that can be used to
run the service. Juju can pull the image directly from dockerhub.

.. code:: bash

    juju deploy ./sunbeam-ironic-operator_ubuntu-20.04-amd64.charm --resource ironic-api-image=kolla/ubuntu-binary-ironic-api:wallaby ironic
    juju add-relation ironic mysql
    juju add-relation ironic keystone
    juju add-relation ironic rabbitmq

Test Service
============

Check that the juju status shows the charms is active and no error messages are
preset. Then check the ironic api service is reponding.

.. code:: bash

    $ juju status ironic
    Model  Controller  Cloud/Region        Version  SLA          Timestamp
    ks     micro       microk8s/localhost  2.9.22   unsupported  13:31:41Z

    App     Version  Status  Scale  Charm                    Store  Channel  Rev  OS          Address        Message
    ironic           active      1  sunbeam-ironic-operator  local             0  kubernetes  10.152.183.73  

    Unit       Workload  Agent  Address       Ports  Message
    ironic/0*  active    idle   10.1.155.106

    $ curl http://10.1.155.106:6385 | jq '.'
    {
      "name": "OpenStack Ironic API",
      "description": "Ironic is an OpenStack project which aims to provision baremetal machines.",
      "default_version": {
        "id": "v1",
        "links": [
          {
            "href": "http://10.1.155.106:6385/v1/",
            "rel": "self"
          }
         ],
        "status": "CURRENT",
        "min_version": "1.1",
        "version": "1.72"
      },
      "versions": [
        {
          "id": "v1",
          "links": [
            {
              "href": "http://10.1.155.106:6385/v1/",
              "rel": "self"
            }
           ],
          "status": "CURRENT",
          "min_version": "1.1",
          "version": "1.72"
        }
      ]
    }
