============================
How-To deploy sunbeam charms
============================

Sunbeam charms requires juju environment with a registered kubernetes cloud.

Below are the steps to deploy sunbeam charms on `juju with microk8s cloud`_
on a single node.

Install microk8s
~~~~~~~~~~~~~~~~

1. Install microk8s snap

   Run below commands to install microk8s snap

.. code-block:: bash

   sudo snap install microk8s --classic
   sudo usermod -a -G microk8s $USER
   sudo chown -f -R $USER ~/.kube
   su - $USER
   microk8s status --wait-ready

2. If required, set proxy variables

   Change the proxy values as per the environment.

.. code-block:: bash

   echo "HTTPS_PROXY=http://squid.internal:3128" >> /var/snap/microk8s/current/args/containerd-env
   echo "NO_PROXY=10.0.0.0/8,192.168.0.0/16,127.0.0.0/8,172.16.0.0/16" >> /var/snap/microk8s/current/args/containerd-env
   sudo systemctl restart snap.microk8s.daemon-containerd.service

3. Enable add-ons

   In the below commands, change the following
   * ``10.245.160.2`` to point to DNS server
   * ``10.5.100.100-10.5.100.110`` to IP range allocations for loadbalancers

.. code-block:: bash

   microk8s enable dns:10.245.160.2
   microk8s enable hostpath-storage
   microk8s enable metallb:10.5.100.100-10.5.100.110

Install juju
~~~~~~~~~~~~

Run below commands to install juju controller on microk8s

.. code-block:: bash

   sudo snap install juju --classic
   juju bootstrap --config controller-service-type=loadbalancer microk8s micro

Deploy Sunbeam charms
~~~~~~~~~~~~~~~~~~~~~

Sample `sunbeam bundle`_ to deploy.

To use locally built charms, update the following in the bundle

* ``charm:`` to point to locally built charm file
* ``channel:`` should be commented

Run below commands to deploy the bundle

.. code-block:: bash

   juju add-model sunbeam
   juju deploy ./sunbeam.yaml --trust

Check ``juju status`` and wait for all units to be active.

Testing OpenStack Control plane
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Install openstackclients snap

.. code-block:: bash

   sudo snap install openstackclients --channel xena/stable

2. Setup novarc file

a. Get keystone service ip

.. code-block:: bash

   juju status keystone | grep keystone-k8s | awk '{print $6}'


b. Update sample novarc file with proper OS_AUTH_URL

.. code-block:: bash

   export OS_AUTH_VERSION=3
   export OS_AUTH_URL=http://10.152.183.109:5000/v3
   export OS_PROJECT_DOMAIN_NAME=admin_domain
   export OS_USERNAME=admin
   export OS_USER_DOMAIN_NAME=admin_domain
   export OS_PROJECT_NAME=admin
   export OS_PASSWORD=abc123
   export OS_IDENTITY_API_VERSION=3

3. Run some openstack commands

.. code-block:: bash

   openstack endpoint list

At this point launching a VM does not work as nova-compute charm does not
support bringing up ovn-controller.


.. _`juju with microk8s cloud`: https://juju.is/docs/olm/microk8s
.. _`sunbeam bundle`: https://opendev.org/openstack/charm-ops-sunbeam/src/branch/main/doc/sunbeam.yaml
