FROM python:3.12-slim

ENV APP_DIR /opt/app
ENV APP_USER user
ENV APP_GROUP group

WORKDIR ${APP_DIR}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=${APP_DIR}

COPY requirements.txt ./

RUN  python3 -m pip install -r requirements.txt

COPY src src

RUN  groupadd -r ${APP_GROUP} && \
     useradd -d ${APP_DIR} -r -g ${APP_GROUP} ${APP_USER} && \
     chown ${APP_USER}:${APP_GROUP} -R ${APP_DIR}

USER ${APP_USER}

ENTRYPOINT ["gunicorn", "src.main:app", "--bind", "0.0.0.0:8000", "--worker-class", "uvicorn.workers.UvicornWorker"]
