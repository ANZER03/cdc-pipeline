FROM apache/spark:3.5.3

USER root

# Install curl to download jars + pip for Python packages
RUN apt-get update && apt-get install -y curl python3-pip && rm -rf /var/lib/apt/lists/*

# Install Python redis client for foreachBatch Redis sink
RUN pip3 install --no-cache-dir redis==5.2.1

# Define versions
ENV SCALA_VERSION=2.12
ENV SPARK_VERSION=3.5.3
ENV CONFLUENT_VERSION=7.7.0
ENV POSTGRESQL_VERSION=42.7.10
ENV SPARK_REDIS_VERSION=3.1.0

# Download Kafka, Avro, and Schema Registry dependencies for Spark
RUN curl -s https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar \
    -o /opt/spark/jars/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar \
    -o /opt/spark/jars/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/spark/spark-avro_${SCALA_VERSION}/${SPARK_VERSION}/spark-avro_${SCALA_VERSION}-${SPARK_VERSION}.jar \
    -o /opt/spark/jars/spark-avro_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar \
    -o /opt/spark/jars/kafka-clients-3.5.1.jar && \
    curl -s https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar \
    -o /opt/spark/jars/commons-pool2-2.11.1.jar && \
    curl -s https://packages.confluent.io/maven/io/confluent/kafka-schema-registry-client/${CONFLUENT_VERSION}/kafka-schema-registry-client-${CONFLUENT_VERSION}.jar \
    -o /opt/spark/jars/kafka-schema-registry-client-${CONFLUENT_VERSION}.jar && \
    curl -s https://packages.confluent.io/maven/io/confluent/kafka-avro-serializer/${CONFLUENT_VERSION}/kafka-avro-serializer-${CONFLUENT_VERSION}.jar \
    -o /opt/spark/jars/kafka-avro-serializer-${CONFLUENT_VERSION}.jar && \
    curl -s https://packages.confluent.io/maven/io/confluent/common-config/${CONFLUENT_VERSION}/common-config-${CONFLUENT_VERSION}.jar \
    -o /opt/spark/jars/common-config-${CONFLUENT_VERSION}.jar && \
    curl -s https://packages.confluent.io/maven/io/confluent/common-utils/${CONFLUENT_VERSION}/common-utils-${CONFLUENT_VERSION}.jar \
    -o /opt/spark/jars/common-utils-${CONFLUENT_VERSION}.jar

# Download PostgreSQL JDBC Driver (keep available for future catalog work)
RUN curl -s https://repo1.maven.org/maven2/org/postgresql/postgresql/${POSTGRESQL_VERSION}/postgresql-${POSTGRESQL_VERSION}.jar \
    -o /opt/spark/jars/postgresql-${POSTGRESQL_VERSION}.jar

# Download spark-redis (with bundled dependencies — includes jedis client)
RUN curl -s https://repo1.maven.org/maven2/com/redislabs/spark-redis_${SCALA_VERSION}/${SPARK_REDIS_VERSION}/spark-redis_${SCALA_VERSION}-${SPARK_REDIS_VERSION}-jar-with-dependencies.jar \
    -o /opt/spark/jars/spark-redis_${SCALA_VERSION}-${SPARK_REDIS_VERSION}-jar-with-dependencies.jar

WORKDIR /opt/spark

USER spark
