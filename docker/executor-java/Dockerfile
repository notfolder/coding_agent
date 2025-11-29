# Java実行環境Dockerfile
# Java 21 LTS (Eclipse Temurin) + Maven + Gradle
# 用途: Java/Kotlinプロジェクト、Spring Boot、Quarkus等

FROM eclipse-temurin:21-jdk-jammy

# メタデータ
LABEL maintainer="coding-agent"
LABEL description="Java development environment for coding agent executor"
LABEL version="1.0"

# 環境変数設定
ENV JAVA_HOME=/opt/java/openjdk
ENV MAVEN_HOME=/opt/maven
ENV GRADLE_HOME=/opt/gradle
ENV PATH="${MAVEN_HOME}/bin:${GRADLE_HOME}/bin:${PATH}"

# Maven と Gradle のバージョン
ARG MAVEN_VERSION=3.9.9
ARG GRADLE_VERSION=8.11.1

# 基本パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Mavenのインストール
RUN mkdir -p ${MAVEN_HOME} && \
    curl -fsSL https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz | \
    tar -xzC ${MAVEN_HOME} --strip-components=1

# Gradleのインストール
RUN mkdir -p ${GRADLE_HOME} && \
    curl -fsSL https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip -o /tmp/gradle.zip && \
    unzip -d /opt /tmp/gradle.zip && \
    mv /opt/gradle-${GRADLE_VERSION}/* ${GRADLE_HOME}/ && \
    rm -rf /tmp/gradle.zip /opt/gradle-${GRADLE_VERSION}

# 作業ディレクトリの作成
RUN mkdir -p /workspace/project /workspace/tmp

WORKDIR /workspace

# コンテナを永続実行するためのコマンド
CMD ["sleep", "infinity"]
