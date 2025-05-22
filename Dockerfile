FROM postgres:17.2

ARG CITUS_VERSION=13.0.3.citus-1

# install Citus and Mobilitydb
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
    && curl -s https://install.citusdata.com/community/deb.sh | bash \
    && apt-get install -y postgresql-17-citus-13.0=$CITUS_VERSION \
                          postgresql-17-hll=2.18.citus-1 \
                          postgresql-17-mobilitydb=1.2.0-2.pgdg120+1 \
                          postgresql-17-postgis-3=3.5.3+dfsg-1~exp1.pgdg120+1 \
                          postgresql-17-topn=2.7.0.citus-1 \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# add citus to default PostgreSQL config
RUN echo "shared_preload_libraries='citus'" >> /usr/share/postgresql/postgresql.conf.sample

# add scripts to run after initdb, adding citus, mobilitydb and citus
COPY 001-create-extensions.sql /docker-entrypoint-initdb.d/

# add health check script
COPY pg_healthcheck wait-for-manager.sh /
RUN chmod +x /wait-for-manager.sh

# entry point unsets PGPASSWORD, but we need it to connect to workers
# https://github.com/docker-library/postgres/blob/33bccfcaddd0679f55ee1028c012d26cd196537d/12/docker-entrypoint.sh#L303
RUN sed "/unset PGPASSWORD/d" -i /usr/local/bin/docker-entrypoint.sh

HEALTHCHECK --interval=4s --start-period=6s CMD ./pg_healthcheck
