-- Register the hostname that future workers will use to connect
-- to the coordinator node.
SELECT citus_set_coordinator_host('coordinator', 5432);

-- Below add all the worker nodes with the following command
-- The worker nodes will be written in here inside docker build stage
