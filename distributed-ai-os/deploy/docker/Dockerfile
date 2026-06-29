# Distributed AI OS node image (Generation 1)
FROM python:3.12-slim

WORKDIR /app

COPY packages/protocol /app/packages/protocol
COPY apps/node /app/apps/node

RUN pip install --no-cache-dir \
    /app/packages/protocol \
    /app/apps/node

EXPOSE 8000 8001 50052

ENTRYPOINT ["daios-node"]
