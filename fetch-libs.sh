#!/bin/bash

charmcraft fetch-lib charms.nginx_ingress_integrator.v0.ingress
charmcraft fetch-lib charms.sunbeam_mysql_k8s.v0.mysql
charmcraft fetch-lib charms.sunbeam_keystone_operator.v0.identity_service
charmcraft fetch-lib charms.sunbeam_rabbitmq_operator.v0.amqp
charmcraft fetch-lib charms.sunbeam_ovn_central_operator.v0.ovsdb
