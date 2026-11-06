FROM alpine:3.24@sha256:3f4d6b32e26703c6082839234f43769d5046b3ac7c910033911d1e71d8cd630a
RUN apk upgrade --no-cache \
 && apk add --no-cache rspamd=4.0.1-r0 ca-certificates python3 \
 && apk info -v > /etc/rspamd/packages.txt
COPY filter/ /opt/oo-filter/
RUN python3 -c 'from pathlib import Path; import shutil; [(shutil.copyfile(p, Path("/etc/rspamd/local.d") / (p.name if p.name.startswith("worker-") else p.stem+".conf"))) for p in Path("/opt/oo-filter").glob("*.inc")]'
EXPOSE 11332 11334
CMD ["python3", "/opt/oo-filter/entrypoint.py"]
