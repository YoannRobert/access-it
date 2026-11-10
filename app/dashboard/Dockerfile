FROM python:3.12-slim

RUN useradd -m -u 1000 user

USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    TZ=Europe/Paris

RUN mkdir $HOME/app

WORKDIR $HOME/app

COPY --chown=user README.md pyproject.toml ./
COPY --chown=user src/ ./src/

RUN pip install --no-cache-dir ".[dashboard]"

COPY --chown=user app/dashboard/ app/dashboard/

EXPOSE 7860

ENTRYPOINT ["streamlit", "run", "app/dashboard/streamlit_app.py", "--server.port=7860", "--server.address=0.0.0.0"]
