#!/bin/bash

# NOTE: this only fetches libs for use in unit tests here.
# Charms that depend on this library should fetch these libs themselves.

echo "WARNING: Charm interface libs are excluded from ASO python package."
charmcraft fetch-lib charms.nginx_ingress_integrator.v0.ingress
charmcraft fetch-lib charms.data_platform_libs.v0.database_requires
charmcraft fetch-lib charms.keystone_k8s.v1.identity_service
charmcraft fetch-lib charms.keystone_k8s.v0.identity_credentials
charmcraft fetch-lib charms.keystone_k8s.v0.identity_resource
charmcraft fetch-lib charms.rabbitmq_k8s.v0.rabbitmq
charmcraft fetch-lib charms.ovn_central_k8s.v0.ovsdb
charmcraft fetch-lib charms.traefik_k8s.v2.ingress
charmcraft fetch-lib charms.ceilometer_k8s.v0.ceilometer_service
charmcraft fetch-lib charms.cinder_ceph_k8s.v0.ceph_access                                                                                                                              
echo "Copying libs to to unit_test dir"
rsync --recursive --delete lib/ tests/lib/
