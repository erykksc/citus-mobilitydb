# Citus Cluster for Kubernetes

This repository contains configuration for deploying a distributed PostgreSQL cluster running MobilityDB using Citus on Kubernetes with automatic worker management.

## Prerequisites

- Kubernetes cluster
- kubectl configured to communicate with your cluster
- Docker (for building custom images)

## Quick Start

1. Deploy the entire Citus cluster:

   ```bash
   kubectl apply -f citus-cluster.yaml
   ```

2. Wait for all pods to be ready:
   ```bash
   kubectl wait --for=condition=ready pod -l app=citus
   kubectl wait --for=condition=ready pod -l app=citus-manager
   ```

## Components

- **Coordinator**: The main PostgreSQL node that coordinates queries
- **Workers**: Distributed PostgreSQL nodes that store sharded data
- **Manager**: Kubernetes-aware service that automatically registers/deregisters worker nodes

## Monitoring

Check the status of your Citus cluster:

```bash
# List all pods in the cluster
kubectl get pods

# Check logs from the manager
kubectl logs -l app=citus-manager

# Check logs from the coordinator
kubectl logs citus-coordinator-0
```

A script for creating a tmux window for monitoring is provided:

```bash
CLUSTERIP=$(minikube ip) ./monitor-deployment.sh
```

## Scaling

To scale the number of worker nodes:

```bash
kubectl scale statefulset citus-worker --replicas=<number>
```

The manager will automatically detect new workers and register them with the coordinator.

## Connecting to the Database

Connect to the coordinator node:

```bash
kubectl exec -it citus-coordinator-0 -- psql -U postgres
```

## Cleanup

To delete the entire Citus cluster:

```bash
kubectl delete -f citus-cluster.yaml
```

## Troubleshooting

If workers aren't being registered:

1. Check manager logs:

   ```bash
   kubectl logs -l app=citus-manager
   ```

2. Verify the manager has the correct permissions:

   ```bash
   kubectl auth can-i get pods --as=system:serviceaccount:default:manager-sa
   ```

3. Check the health check file:
   ```bash
   kubectl exec -it $(kubectl get pod -l app=citus-manager -o name) -- cat /healthcheck/manager-ready
   ```

## Manager migration

> The manager script and its dockerfile has been moved to a [https://github.com/erykksc/citus-k8s-manager](https://github.com/erykksc/citus-k8s-manager)
