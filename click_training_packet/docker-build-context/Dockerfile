# syntax=docker/dockerfile:1
FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5

# Build tools allow sqlite3 to compile if no compatible prebuilt binary exists.
RUN apk add --no-cache git python3 make g++
WORKDIR /app
RUN git clone https://github.com/docker/getting-started-app.git . \
    && git checkout --detach 6b025fc53bc7b9bef435d6b09bcd1da5a871c9cc \
    && rm -rf .git

# Newer npm releases require explicit permission for native install scripts.
# Older releases ignore this field. Dependency versions remain in the lockfile.
RUN node -e 'const fs = require("fs"); const p = JSON.parse(fs.readFileSync("package.json", "utf8")); p.allowScripts = {"sqlite3@5.1.7": true}; fs.writeFileSync("package.json", JSON.stringify(p, null, 2));'
RUN npm ci --omit=dev

# .dockerignore excludes the Dockerfile and includes the hidden .opencode folder.
COPY . .
EXPOSE 3000
CMD ["node", "src/index.js"]
