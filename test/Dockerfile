FROM apache/spark:3.5.3

USER root

# Install curl to download jars
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Define versions
ENV ICEBERG_VERSION=1.7.1
ENV SCALA_VERSION=2.12
ENV SPARK_VERSION=3.5.3

# Download Iceberg Spark Runtime
RUN curl -s https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_${SCALA_VERSION}/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_${SCALA_VERSION}-${ICEBERG_VERSION}.jar \
    -o /opt/spark/jars/iceberg-spark-runtime-3.5_${SCALA_VERSION}-${ICEBERG_VERSION}.jar

# Download Kafka Connectors (Spark SQL Kafka and its dependencies)
RUN curl -s https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar \
    -o /opt/spark/jars/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar \
    -o /opt/spark/jars/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar \
    -o /opt/spark/jars/kafka-clients-3.5.1.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar \
    -o /opt/spark/jars/commons-pool2-2.11.1.jar

WORKDIR /opt/spark

USER spark
