#!/usr/bin/env python3

import os
import signal
from sys import exit, stderr
from time import sleep

import psycopg2
from kubernetes import client, config, watch

HEALTHCHECK_FILE = '/healthcheck/manager-ready'

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


def add_worker(conn, ip):
    cur = conn.cursor()
    try:
        cur.execute("SELECT master_add_node(%s, %s)", (ip, 5432))
        print(f"Worker {ip} added successfully", file=stderr)
    except Exception as e:
        print(f"Error adding worker {ip}: {e}", file=stderr)
        raise e


def remove_worker(conn, ip):
    print(f"Worker {ip} removed from the cluster, doing nothing", file=stderr)


def graceful_shutdown(signalnum, frame):
    print("Shutting down...", file=stderr)
    exit(0)


def discover_existing_workers(k8s, namespace, label_selector, conn):
    """Find all existing running worker pods and add them to the cluster"""
    print("Discovering existing worker pods...", file=stderr)
    pods = k8s.list_namespaced_pod(
        namespace=namespace, label_selector=label_selector)

    for pod in pods.items:
        if pod.status.phase == "Running" and pod.status.pod_ip:
            print(
                f"Discovered existing worker: {pod.status.pod_ip}", file=stderr)
            add_worker(conn, pod.status.pod_ip)


def watch_workers():
    config.load_incluster_config()
    k8s = client.CoreV1Api()
    w = watch.Watch()

    label_selector = 'app=citus,role=worker'
    namespace = os.environ.get("POD_NAMESPACE", "default")
    conn = connect_to_master()

    # First discover existing workers
    discover_existing_workers(k8s, namespace, label_selector, conn)

    # Signal ready for readiness/liveness probes
    open(HEALTHCHECK_FILE, 'a').close()
    print("Watching for worker pod events...", file=stderr)

    try:
        for event in w.stream(k8s.list_namespaced_pod, namespace=namespace, label_selector=label_selector):
            obj = event['object']
            pod_ip = obj.status.pod_ip
            pod_phase = obj.status.phase
            event_type = event['type']
            pod_name = obj.metadata.name

            if pod_ip is None:
                continue

            # Handle pod added or modified to Running state
            if event_type in ["ADDED", "MODIFIED"] and pod_phase == "Running":
                print(
                    f"Pod {pod_name} is running with IP {pod_ip}", file=stderr)
                add_worker(conn, pod_ip)
            elif event_type == "DELETED":
                print(f"Pod {pod_name} was deleted", file=stderr)
                remove_worker(conn, pod_ip)

    except Exception as e:
        print(f"Exception while watching pods: {e}", file=stderr)
        # Let the pod die so Kubernetes can restart it
        raise


def main():
    if os.path.exists(HEALTHCHECK_FILE):
        os.remove(HEALTHCHECK_FILE)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    watch_workers()


if __name__ == "__main__":
    main()
