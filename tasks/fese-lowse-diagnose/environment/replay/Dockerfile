FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
COPY mbe_replay_env.py replay_server.py /srv/replay/
COPY data /srv/replay/data
EXPOSE 8080
CMD ["python3", "-I", "/srv/replay/replay_server.py"]
