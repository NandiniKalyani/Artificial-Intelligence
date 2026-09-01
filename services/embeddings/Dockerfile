FROM python:3.11-slim

WORKDIR /app

# torch comes in as a dependency and pulls the CUDA wheels by default, which is
# 2GB of GPU libraries this will never use. The cpu index gives the small one
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# bake the model into the image. It is only about 90MB and this way a clean
# clone behaves the same as my machine, with no download on first start and no
# cache volume to keep in sync
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app.py .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
