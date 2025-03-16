FROM python:3.12

# 環境変数設定
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8
ENV TZ=Asia/Tokyo

# 必要なパッケージをインストール
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ作成
WORKDIR /workspace

# 必要なPythonパッケージをインストール
COPY requirements.txt /workspace/
RUN pip install --no-cache-dir -r requirements.txt

# 実行ユーザーを変更（オプション）
RUN useradd -m devuser && chown -R devuser /workspace
USER devuser

CMD ["bash"]
