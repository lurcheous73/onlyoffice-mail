FROM mariadb:11.8.9@sha256:c4124d1afa875e47f2892edf26b482fa54f796e2f342d3717a04ca091a22a9bd
ENV DEBIAN_FRONTEND=noninteractive
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
 && apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends python3 \
 && mkdir -p /run/mysqld /opt/oo-db && chown mysql:mysql /run/mysqld \
 && dpkg-query -W > /opt/oo-db/packages.txt && apt-get clean
# This image uses its own root-to-mysqld startup; the upstream Go-based privilege
# helper is unused. Exclude that executable from the runtime attack surface.
RUN rm -f /usr/local/bin/gosu
COPY db/ /opt/oo-db/
EXPOSE 3306
ENTRYPOINT ["python3", "/opt/oo-db/entrypoint.py"]
