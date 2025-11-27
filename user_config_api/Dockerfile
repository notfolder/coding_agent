FROM python:3.13-slim

WORKDIR /app

# システム依存関係のインストール（python-ldap、pandas用）
RUN apt-get update && apt-get install -y \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY server.py .
COPY streamlit_app.py .
COPY config.yaml .
COPY app/ ./app/
COPY api/ ./api/
COPY streamlit_custom/ ./streamlit_custom/

# データディレクトリを作成
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
