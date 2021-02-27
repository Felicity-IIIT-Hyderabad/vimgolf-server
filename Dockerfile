FROM python:3.8-slim

WORKDIR /opt

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt update && \
    apt install -y gcc && \
    rm -rf /var/lib/apt/lists

COPY requirements.txt /opt
RUN pip install --no-cache-dir -r /opt/requirements.txt uwsgi

COPY . /opt

ENV PYTHONPATH=/opt
CMD ["uwsgi", "--http", ":4242", "--manage-script-name", "-b", "32768", "--master", "--processes", "4", "--threads", "2", "--mount", "/vimgolf=vimgolf.app:app"]
