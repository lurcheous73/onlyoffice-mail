FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends python3 python3-flask python3-waitress python3-pymysql python3-requests python3-cryptography ca-certificates \
 && useradd -u 5000 -d /nonexistent -s /usr/sbin/nologin mailapi \
 && mkdir -p /opt/oo-api && dpkg-query -W > /opt/oo-api/packages.txt && apt-get clean
COPY api/ /opt/oo-api/
RUN chmod -R a+rX /opt/oo-api && mkdir /dkim && chown 5000:5000 /dkim
WORKDIR /opt/oo-api
USER 5000:5000
EXPOSE 8081
CMD ["python3", "server.py"]
