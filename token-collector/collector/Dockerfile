# 커스텀 Collector(otelcol-agentscope) 컨테이너 이미지.
#
# 빌드 컨텍스트는 이 폴더(token-collector/collector). 보통은 pipeline/docker-compose.yml이
# 알아서 빌드하므로 직접 실행할 일은 없다. 직접 빌드하려면:
#   docker build -t agentscope/otelcol-agentscope:local token-collector/collector
#
# 1단계: OCB(OpenTelemetry Collector Builder)로 builder-config.yaml대로 소스를 생성하고 컴파일한다.
#        Go 1.26 이상 필요(Collector v0.161.0 요구사항). 실행 파일은 커밋하지 않으므로 이미지 안에서 빌드한다.
FROM golang:1.26-alpine AS build
RUN apk add --no-cache git
RUN go install go.opentelemetry.io/collector/cmd/builder@v0.161.0
WORKDIR /src
COPY attribution ./attribution
COPY tokenattributionconnector ./tokenattributionconnector
COPY builder-config.yaml ./
ENV CGO_ENABLED=0
RUN builder --config builder-config.yaml

# 2단계: 실행 파일만 담은 작은 이미지.
FROM alpine:3.22
COPY --from=build /src/_build/otelcol-agentscope /usr/local/bin/otelcol-agentscope
# 4318: OTLP/HTTP 수신, 9464: Prometheus가 긁어가는 /metrics
EXPOSE 4318 9464
ENTRYPOINT ["/usr/local/bin/otelcol-agentscope"]
CMD ["--config=/etc/otelcol-config.yaml"]
