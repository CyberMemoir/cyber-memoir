# MinIO's community registry image is no longer publicly pullable. Build the
# official source-only security release, and reject a moved release tag.
FROM golang:1.24.8-bookworm AS build
WORKDIR /src
RUN git clone --depth 1 --branch RELEASE.2025-10-15T17-29-55Z https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = "9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/doc/minio/LICENSE
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
