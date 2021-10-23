=============
New API Charm
=============

The example below will walk through the creation of a basic API charm for the
OpenStack `Glance <https://wiki.openstack.org/wiki/Glance>`__ service.

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

Metadata
~~~~~~~~

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
~~~~~~~~~~~~

.. code:: bash

    cp advanced-sunbeam-openstack/tox.ini charm-glance-operator/tox.ini
    cp advanced-sunbeam-openstack/requirements.txt charm-glance-operator/requirements.txt 
    cp -r advanced-sunbeam-openstack/templates charm-glance-operator/src/

Fetch interface libs corresponding to the requires interfaces:

.. code:: bash

    charmcraft fetch-lib charms.nginx_ingress_integrator.v0.ingress
    charmcraft fetch-lib charms.sunbeam_mysql_k8s.v0.mysql
    charmcraft fetch-lib charms.sunbeam_keystone_operator.v0.identity_service
    charmcraft fetch-lib charms.sunbeam_rabbitmq_operator.v0.amqp
    charmcraft fetch-lib charms.observability_libs.v0.kubernetes_service_patch

