Some miscellaneous debugging notes.

## stuck on ``waiting ... installing agent``.

If many units are stuck in waiting status at the installing agent step,
and traefik charms have the status message "gateway address unavailable",
then check that the k8s undercloud has a form of ingress enabled.

An easy way to enable ingress with microk8s
is to enable metallb, and give it a block of ip addresses.
Currently these ip addresses aren't used for anything with sunbeam,
so it doesn't matter what you use.
A simple option is to pick a small range on your current LAN for example.


## Accessing remote microk8s

If you have microk8s running on a remote server,
and you want to access it from juju and the openstack client locally,
here are some guidelines.

1. Run `microk8s.config` on the remote server.
2. Copy the output to `~/.kube/config` on your local machine (so we now have credentials).
3. Edit `~/.kube/config` and update the server url/ip to point to the remote server.
4. Check firewall rules on the remote server to ensure you'll have access to the k8s and openstack ports.
5. Add a standard k8s cluster to your local juju client: `juju add-k8s my-microk8s`
6. At this point the k8s cloud is registered and you can deploy bundles with juju.
7. To access the sunbeam openstack you will need some kind of routing though.
   `sshuttle` is a useful and simple tool to achieve this.  Try `sshuttle -r <remote_server> <subnet_to_forward>`.
   Eg. `sshuttle -r ubuntu@192.168.1.103 10.152.0.0/16`, assuming that 10.152.0.0/16 is the local subnet on the remote server allocated to microk8s pods.


## Cannot launch openstack instances.

It's a known issue that currently it's impossible to launch instances with the sunbeam openstack.
Most other things should work though.
