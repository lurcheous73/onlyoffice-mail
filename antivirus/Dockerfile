FROM clamav/clamav:1.5.4_base@sha256:58168cd4f48a118c7d20b76da8ffce97e579b84ed7e6d1e977c6e22b1e989c5a
RUN apk upgrade --no-cache && apk add --no-cache python3 ca-certificates \
 && mkdir -p /opt/oo-av /etc/clamav \
 && apk info -v > /opt/oo-av/packages.txt
COPY antivirus/ /opt/oo-av/
EXPOSE 3310
ENTRYPOINT ["python3", "/opt/oo-av/entrypoint.py"]
CMD []
