FROM debezium/connect:2.3

USER root

ENV CONFLUENT_VERSION=7.7.0
ENV AVRO_VERSION=1.11.3

RUN microdnf install -y unzip && microdnf clean all && \
    mkdir -p /kafka/connect/confluent-avro && \
    curl -sL "https://hub-downloads.confluent.io/api/plugins/confluentinc/kafka-connect-avro-converter/versions/${CONFLUENT_VERSION}/confluentinc-kafka-connect-avro-converter-${CONFLUENT_VERSION}.zip" \
      -o /tmp/confluent-avro.zip && \
    unzip -q /tmp/confluent-avro.zip -d /kafka/connect/confluent-avro && \
    curl -sL "https://repo1.maven.org/maven2/org/apache/avro/avro/${AVRO_VERSION}/avro-${AVRO_VERSION}.jar" \
      -o /kafka/connect/confluent-avro/avro-${AVRO_VERSION}.jar && \
    rm -f /tmp/confluent-avro.zip

USER kafka
