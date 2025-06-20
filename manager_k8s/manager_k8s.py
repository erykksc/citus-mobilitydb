#!/usr/bin/env python3

import logging
import os
import signal
from sys import exit
from time import sleep

import psycopg2
from kubernetes import client, config

HEALTHCHECK_FILE = "/healthcheck/manager-ready"
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "20"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# Connect to Citus master
def connect_to_master():
    citus_host = os.environ.get("CITUS_HOST")
    postgres_pass = os.environ.get("POSTGRES_PASSWORD")
    postgres_user = os.environ.get("POSTGRES_USER")
    postgres_db = os.environ.get("POSTGRES_DB")

    conn = None
    while conn is None:
        try:
            conn = psycopg2.connect(
                dbname=postgres_db,
                user=postgres_user,
                host=citus_host,
                password=postgres_pass,
            )
        except psycopg2.OperationalError:
            logger.warning(f"Could not connect to {citus_host}, retrying...")
            sleep(1)
        except Exception as e:
            raise e
    conn.autocommit = True
    logger.info(f"Connected to {citus_host}")
    return conn


def get_citus_nodes(conn):
    """Get list of worker nodes registered in Citus"""
    try:
        cur = conn.cursor()
        cur.execute("SELECT nodename FROM pg_dist_node WHERE nodeport = 5432")
        return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error getting Citus nodes: {e}")
        return []


def add_worker(conn, ip):
    """Add a worker node to the Citus cluster"""
    cur = conn.cursor()
    try:
        # Check if node already exists
        cur.execute(
            "SELECT nodeid FROM pg_dist_node WHERE nodename = %s AND nodeport = 5432",
            (ip,),
        )
        if cur.fetchone() is None:
            # Node doesn't exist, add it
            cur.execute("SELECT master_add_node(%s, %s)", (ip, 5432))
            logger.info(f"Worker {ip} added successfully")
        else:
            logger.info(f"Worker {ip} already exists in the cluster")
    except Exception as e:
        logger.error(f"Error adding worker {ip}: {e}")
        # Don't raise the exception to avoid crashing the manager


def graceful_shutdown(signalnum, frame):
    """Handle graceful shutdown on SIGTERM"""
    logger.info("Shutting down...")
    exit(0)


def get_ready_worker_pods(k8s, namespace, label_selector):
    """Get all ready worker pods in the namespace"""
    pods = k8s.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

    ready_pods = []
    for pod in pods.items:
        is_ready = False
        if pod.status.conditions:
            for condition in pod.status.conditions:
                if condition.type == "Ready" and condition.status == "True":
                    is_ready = True
                    break

        if pod.status.phase == "Running" and pod.status.pod_ip and is_ready:
            ready_pods.append(pod)

    return ready_pods


def sync_workers(k8s, namespace, label_selector, conn):
    """Synchronize Kubernetes worker pods with Citus nodes"""
    logger.info("Synchronizing worker nodes...")

    # Get current Citus nodes
    citus_nodes = get_citus_nodes(conn)
    logger.info(f"Current Citus nodes: {citus_nodes}")

    # Get ready worker pods
    ready_pods = get_ready_worker_pods(k8s, namespace, label_selector)
    ready_pod_ips = [pod.status.pod_ip for pod in ready_pods]
    logger.info(f"Ready worker pods: {ready_pod_ips}")

    # Add missing workers
    for pod in ready_pods:
        if pod.status.pod_ip not in citus_nodes:
            logger.info(f"Adding missing worker: {pod.status.pod_ip}")
            add_worker(conn, pod.status.pod_ip)


def watch_workers():
    """Periodically check for worker pods and manage Citus cluster membership"""
    config.load_incluster_config()
    k8s = client.CoreV1Api()

    namespace = os.environ.get("POD_NAMESPACE")

    label_selector = os.environ.get("LABEL_SELECTOR")
    if label_selector == None:
        raise ValueError(
            "LABEL_SELECTOR environment variable must be set to be able to find mobilitydbc worker nodes"
        )

    conn = connect_to_master()

    # Signal ready for readiness/liveness probes
    open(HEALTHCHECK_FILE, "a").close()

    manager_config = {
        "namespace": namespace,
        "label_selector": label_selector,
        "scan_interval": SCAN_INTERVAL_SECONDS,
    }
    logger.info(
        f"Starting periodic worker synchronization with config: {manager_config}",
    )
    while True:
        try:
            sync_workers(k8s, namespace, label_selector, conn)
            sleep(SCAN_INTERVAL_SECONDS)

        except Exception as e:
            logger.error(f"Error during sync: {e}")
            # Let the pod die so Kubernetes can restart it
            raise


def main():
    if os.path.exists(HEALTHCHECK_FILE):
        os.remove(HEALTHCHECK_FILE)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    watch_workers()


if __name__ == "__main__":
    main()
