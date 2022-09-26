=================
Reference Bundles
=================

There are some official reference bundles in `./bundles/`:


`minimal.yaml`
~~~~~~~~~~~~~~

The baseline "here's a barebones OpenStack" that can be deployed on a k8s cloud.


`full.yaml`
~~~~~~~~~~~

All the things that can be deployed on a k8s cloud.
As-is, `cinder-ceph` will not come up active
because it requires a relation to a `ceph-mon`.
However this may be replaced with some configuration
to connect to https://github.com/canonical/microceph in the future.
