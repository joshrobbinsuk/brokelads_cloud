# Firebase Auth emulator for local dev. The auth emulator needs a JRE (Java);
# firebase-tools is pinned so the local pool behaviour is reproducible.
FROM node:20-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g firebase-tools@13.29.1

WORKDIR /srv
COPY firebase.json ./

EXPOSE 9099

CMD ["firebase", "emulators:start", "--only", "auth", "--project", "demo-brokelads"]
