FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ENV DEBIAN_FRONTEND=noninteractive
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
 && apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends postfix postfix-mysql dovecot-core dovecot-imapd dovecot-pop3d dovecot-lmtpd dovecot-mysql dovecot-sieve dovecot-managesieved python3 python3-pymysql python3-argon2 supervisor ca-certificates openssl \
 && groupadd -g 5000 vmail && useradd -u 5000 -g 5000 -d /var/vmail -s /usr/sbin/nologin vmail \
 && mkdir -p /var/vmail /run/oo-mail /opt/oo-mail /etc/postfix/sql \
 && rm -f /etc/ssl/private/ssl-cert-snakeoil.key /etc/ssl/certs/ssl-cert-snakeoil.pem \
 && dpkg-query -W > /opt/oo-mail/packages.txt \
 && apt-get clean
COPY mail/ /opt/oo-mail/
COPY api/common.py /opt/oo-mail/common.py
RUN python3 /opt/oo-mail/install_client.py
RUN chmod 755 /opt/oo-mail/entrypoint.py
EXPOSE 25 143 465 587 993 995 4190
ENTRYPOINT ["/opt/oo-mail/entrypoint.py"]
