FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e . streamlit
COPY agents_wrangler /app/agents_wrangler
EXPOSE 8501
CMD ["streamlit", "run", "agents_wrangler/ui_streamlit.py", "--server.address=0.0.0.0", "--server.port=8501"]
