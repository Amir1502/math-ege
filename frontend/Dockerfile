FROM node:26-alpine@sha256:c6ad9e9c1d80f6eb607c26b4b0a132ff7a2344fad1c78ea3baa2a7d4c8de6d94 AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM nginx/nginx-unprivileged:stable-alpine@sha256:44e74ca483234093081138b6d7b6f561d55557756a2deefc3a5056148defeb99
COPY infra/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
