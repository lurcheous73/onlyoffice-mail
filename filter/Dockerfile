FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends rspamd ca-certificates python3 \
 && dpkg-query -W > /etc/rspamd/packages.txt && apt-get clean
COPY filter/ /opt/oo-filter/
RUN python3 -c 'from pathlib import Path; import shutil; [(shutil.copyfile(p, Path("/etc/rspamd/local.d") / (p.name if p.name.startswith("worker-") else p.stem+".conf"))) for p in Path("/opt/oo-filter").glob("*.inc")]'
EXPOSE 11332 11334
CMD ["python3", "/opt/oo-filter/entrypoint.py"]
