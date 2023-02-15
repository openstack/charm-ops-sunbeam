======================================
How-To expose a service outside of K8S
======================================

++++++++
Overview
++++++++

When Juju deploys an Operator Charm to Kubernetes by default a
ClusterIP service entry is created for each application to provide
resilient, load balanced access to the services it provides from
within the Kubernetes deployment.

For the majority of OpenStack API services external ingress access
is required to the API endpoints from outside of Kubernetes - this
is used by both end-users of the cloud as well as from machine
based charms supporting OpenStack Hypervisors.

Operator charms for API or other web services written using Sunbeam
OpenStack will automatically patch the Juju created service entry to
be of type LoadBalancer, enabling Kubernetes to expose the service to
the outside world using a suitable Load Balancer implementation.

++++++++
MicroK8S
++++++++

For a MicroK8S deployment on bare metal MetalLB can be enabled to
support this feature:

.. code-block:: none

    microk8s enable metallb

by default Microk8s will prompt for an IP address pool for MetalLB
to use - this can also be provided in the enable command:

.. code-block:: none

    microk8s enable metallb:10.64.140.43-10.64.140.49

Please refer to the `MicroK8S MetalLB add-on`_ documentation for more
details.

++++++++++++++++++
Charmed Kubernetes
++++++++++++++++++

For a Charmed Kubernetes deployment on bare metal MetalLB can also be
used for creation of LoadBalancer access to services.

`Operator Charms for MetalLB`_ exist but don't yet support BGP mode for
ECMP (Equal Cost Multi Path) based load balancing by integrating directly
into the network infrastructure hosting the Kubernetes deployment.

For this reason its recommended to use the upstream manifests for
deployment of MetalLB with a suitable ConfigMap for the BGP network
configuration or Layer 2 configuration depending on the mode of
operation desired:

.. code-block:: none

    kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.9.3/manifests/namespace.yaml
    kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.9.3/manifests/metallb.yaml
    # On first install only
    kubectl create secret generic -n metallb-system memberlist --from-literal=secretkey="$(openssl rand -base64 128)"

Example ConfigMap for configuration of MetalLB in BGP mode:

.. code-block:: yaml

    apiVersion: v1
    kind: ConfigMap
    metadata:
      namespace: metallb-system
      name: config
    data:
      config: |
        peers:
        - peer-address: 10.0.0.1
          peer-asn: 64512
          my-asn: 64512
        address-pools:
        - name: default
          protocol: bgp
          addresses:
          - 10.64.140.43-10.64.140.49

IP address pools and BGP peer configuration will be entirely
deployment specific.

++++++++++++++
Service Access
++++++++++++++

Once MetalLB has created a LoadBalancer configuration for a service its
external IP address will be populated in the service entry. Juju will
automatically pick this address for use as the ingress address for the
service on relations (which is not ideal for service communication
within the Kubernetes deployment)

The IP address can also be discovered using the juju status command -
the Load Balancer external IP will be detailed in the application
information:

.. code-block:: none

    $ juju status cinder
    Model    Controller  Cloud/Region       Version  SLA          Timestamp
    sunbeam  maas-one    k8s-cloud/default  2.9.22   unsupported  11:21:51Z

    App     Version  Status   Scale  Charm                    Store  Channel  Rev  OS          Address    Message
    cinder           waiting      1  sunbeam-cinder-operator  local             0  kubernetes  10.0.0.40  installing agent

    Unit       Workload  Agent  Address      Ports  Message
    cinder/0*  unknown   idle   10.1.73.176

.. LINKS
.. _MicroK8S MetalLB add-on: https://microk8s.io/docs/addon-metallba
.. _Operator Charms for MetalLB: https://ubuntu.com/kubernetes/docs/metallb
