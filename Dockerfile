# LoanMate AI backend: FastAPI API + Gemini Live voice worker in one container.
# Built for Hugging Face Spaces (Docker SDK), which serves port 7860 and runs
# containers as user 1000. See DEPLOY.md.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user requirements-deploy.txt .
RUN pip install -r requirements-deploy.txt

COPY --chown=user backend ./backend
COPY --chown=user prompts ./prompts
COPY --chown=user deploy/start.sh ./start.sh
# Strip Windows line endings so the script runs whatever the checkout settings.
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

USER user
EXPOSE 7860
CMD ["./start.sh"]
