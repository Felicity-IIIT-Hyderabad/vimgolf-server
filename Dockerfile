FROM python:3.8-slim

WORKDIR /opt

RUN apt update && \
    apt install -y gcc && \
    rm -rf /var/lib/apt/lists

COPY requirements.txt /opt
RUN pip install --no-cache-dir -r /opt/requirements.txt uwsgi

COPY . /opt

ENV PYTHONPATH=/opt
CMD ["uwsgi", "--http", ":4242", "--manage-script-name", "-b", "32768", "--mount", "/vimgolf=vimgolf.app:app"]
