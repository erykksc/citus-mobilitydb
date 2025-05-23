#!/usr/bin/env python3

import os
import signal
from sys import exit, stderr
from time import sleep

import psycopg2
from kubernetes import client, config

HEALTHCHECK_FILE = '/healthcheck/manager-ready'

# Default scan interval in seconds
DEFAULT_SCAN_INTERVAL = 20

# Connect to Citus master


def connect_to_master():
    citus_host = os.environ.get('CITUS_HOST', 'master')
    postgres_pass = os.environ.get('POSTGRES_PASSWORD', '')
    postgres_user = os.environ.get('POSTGRES_USER', 'postgres')
    postgres_db = os.environ.get('POSTGRES_DB', postgres_user)

    conn = None
    while conn is None:
        try:
            conn = psycopg2.connect(
                dbname=postgres_db,
                user=postgres_user,
                host=citus_host,
                password=postgres_pass
            )
        except psycopg2.OperationalError:
            print(
                f"Could not connect to {citus_host}, retrying...", file=stderr)
            sleep(1)
        except Exception as e:
            raise e
    conn.autocommit = True
    print(f"Connected to {citus_host}", file=stderr)
    return conn


def get_citus_nodes(conn):
    """Get list of worker nodes registered in Citus"""
    try:
        cur = conn.cursor()
        cur.execute("SELECT nodename FROM pg_dist_node WHERE nodeport = 5432")
        return [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error getting Citus nodes: {e}", file=stderr)
        return []


def add_worker(conn, ip):
    """Add a worker node to the Citus cluster"""
    cur = conn.cursor()
    try:
        # Check if node already exists
        cur.execute(
            "SELECT nodeid FROM pg_dist_node WHERE nodename = %s AND nodeport = 5432", (ip,))
        if cur.fetchone() is None:
            # Node doesn't exist, add it
            cur.execute("SELECT master_add_node(%s, %s)", (ip, 5432))
            print(f"Worker {ip} added successfully", file=stderr)
        else:
            print(f"Worker {ip} already exists in the cluster", file=stderr)
    except Exception as e:
        print(f"Error adding worker {ip}: {e}", file=stderr)
        # Don't raise the exception to avoid crashing the manager


def graceful_shutdown(signalnum, frame):
    """Handle graceful shutdown on SIGTERM"""
    print("Shutting down...", file=stderr)
    exit(0)


def get_ready_worker_pods(k8s, namespace, label_selector):
    """Get all ready worker pods in the namespace"""
    pods = k8s.list_namespaced_pod(
        namespace=namespace, label_selector=label_selector)

    ready_pods = []
    for pod in pods.items:
        is_ready = False
        if pod.status.conditions:
            for condition in pod.status.conditions:
                if condition.type == 'Ready' and condition.status == 'True':
                    is_ready = True
                    break

        if pod.status.phase == "Running" and pod.status.pod_ip and is_ready:
            ready_pods.append(pod)

    return ready_pods


def sync_workers(k8s, namespace, label_selector, conn):
    """Synchronize Kubernetes worker pods with Citus nodes"""
    print("Synchronizing worker nodes...", file=stderr)

    # Get current Citus nodes
    citus_nodes = get_citus_nodes(conn)
    print(f"Current Citus nodes: {citus_nodes}", file=stderr)

    # Get ready worker pods
    ready_pods = get_ready_worker_pods(k8s, namespace, label_selector)
    ready_pod_ips = [pod.status.pod_ip for pod in ready_pods]
    print(f"Ready worker pods: {ready_pod_ips}", file=stderr)

    # Add missing workers
    for pod in ready_pods:
        if pod.status.pod_ip not in citus_nodes:
            print(f"Adding missing worker: {pod.status.pod_ip}", file=stderr)
            add_worker(conn, pod.status.pod_ip)


def watch_workers():
    """Periodically check for worker pods and manage Citus cluster membership"""
    config.load_incluster_config()
    k8s = client.CoreV1Api()

    label_selector = 'app=citus,role=worker'
    namespace = os.environ.get("POD_NAMESPACE", "default")
    conn = connect_to_master()

    # Get scan interval from environment variable or use default
    scan_interval = int(os.environ.get(
        "SYNC_INTERVAL_SECONDS", DEFAULT_SCAN_INTERVAL))
    print(f"Using sync interval of {scan_interval} seconds", file=stderr)

    # Signal ready for readiness/liveness probes
    open(HEALTHCHECK_FILE, 'a').close()
    print("Starting periodic worker synchronization...", file=stderr)

    while True:
        try:
            sync_workers(k8s, namespace, label_selector, conn)
            sleep(scan_interval)

        except Exception as e:
            print(f"Error during sync: {e}", file=stderr)
            # Let the pod die so Kubernetes can restart it
            raise


def main():
    if os.path.exists(HEALTHCHECK_FILE):
        os.remove(HEALTHCHECK_FILE)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    watch_workers()


if __name__ == "__main__":
    main()
