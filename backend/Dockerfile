FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required to build webrtcvad
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from pocket_tts import TTSModel; TTSModel.load_model()"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]