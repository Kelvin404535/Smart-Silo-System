FROM python:3.11-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ ./

EXPOSE 8080

CMD ["sh", "-c", "gunicorn \"run:app\" --bind 0.0.0.0:$PORT --workers 1 --timeout 120"]
