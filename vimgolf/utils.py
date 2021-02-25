import os
import time
from typing import Tuple

import docker

VIM_DOCKER_IMAGE = "yoogottamk/vim"
DOCKER_HOST = os.getenv("DOCKER_HOST", "tcp://vim-docker:2375")


def docker_init():
    while True:
        try:
            return docker.DockerClient(base_url=DOCKER_HOST)
        except Exception as e:
            print(e)
            print("Error while connecting to docker client")
            time.sleep(5)
            print("Retrying...")


def get_scores(d: docker.DockerClient, path: str) -> Tuple[Tuple[int, int], str]:
    d.images.pull(VIM_DOCKER_IMAGE)

    run_logs = d.containers.run(
        image=VIM_DOCKER_IMAGE,
        name=path.replace("/", ""),
        remove=True,
        command="/scorer/eval.sh",
        volumes={path: {"bind": "/scorer/files", "mode": "rw"}},
    )

    lines = run_logs.decode("utf-8").strip().split("\n")
    scores = lines[-1].split(" ")

    # (corr, wrong), logs
    return (int(scores[0][1:]), int(scores[1][1:])), "\n".join(lines)
