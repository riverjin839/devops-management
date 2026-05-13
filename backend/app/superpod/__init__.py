"""Super pod — deep check execution entrypoint.

Two modes share the same Docker image as the backend (kubectl + k8s SDK +
ansible already baked in):

* ``SUPERPOD_MODE=in_cluster``: deployed into a target cluster as a CronJob.
  Uses the in-cluster ServiceAccount and POSTs results back to the backend.
* ``SUPERPOD_MODE=centralized``: runs in the management cluster with stored
  kubeconfigs. Useful for clusters we cannot deploy a pod into.
"""
