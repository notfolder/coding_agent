# 親ディレクトリのDockerfileをベースにする
FROM condaforge/miniforge3

ENV PYTHONUNBUFFERED=1
RUN mkdir -p /logs

# Node.js, npm, git, Dockerクライアント、openssh-clientをインストール
RUN apt-get update --allow-insecure-repositories && \
    apt-get install -y --allow-unauthenticated \
    nodejs npm git docker.io openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Python依存パッケージのインストール
COPY condaenv.yaml /tmp/condaenv.yaml
RUN conda env create -f /tmp/condaenv.yaml
SHELL ["conda", "run", "-n", "coding-agent", "/bin/bash", "-c"]

# SSH設定ディレクトリを作成
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# known_hostsの設定(GitHub/GitLabを追加)
RUN ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null && \
    ssh-keyscan gitlab.com >> /root/.ssh/known_hosts 2>/dev/null || true

# 作業ディレクトリ
WORKDIR /app

# conda環境でPythonスクリプトを実行するためのエントリーポイント
ENTRYPOINT ["conda", "run", "-n", "coding-agent", "--no-capture-output"]
