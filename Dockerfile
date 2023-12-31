FROM python:3.11-alpine

COPY ./requirements.txt /tmp/requirements.txt

RUN pip install -r /tmp/requirements.txt

COPY ./main.py /app/main.py

COPY ./config.yaml /app/config/config.yaml

RUN adduser -D -H -u 3737 python python; \
    mkdir -m 750 /app/db; \
    chown -R python:python /app; \
    chmod -R 750 /app

USER python

WORKDIR /app

CMD ["/usr/local/bin/python3 /app/main.py"]