FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 IS_SANDBOX=1
ARG INSTALL_AGENT=0
# optional: preinstall the Claude Code harness (pinned) for agent trials; no credentials in the image
RUN if [ "$INSTALL_AGENT" = "1" ]; then \
      pip install -q --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple nodejs-wheel==24.* && \
      npm install -g --prefix /usr/local --registry=https://registry.npmmirror.com @anthropic-ai/claude-code@2.1.292 && \
      claude --version; fi
COPY fese-lab /usr/local/bin/fese-lab
COPY docs /app/docs
RUN chmod 755 /usr/local/bin/fese-lab
WORKDIR /app
ENV FESE_REPLAY_URL=http://replay:8080
