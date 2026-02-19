FROM apache/spark:3.5.3

USER root

# Install curl to download jars + pip for Python packages
RUN apt-get update && apt-get install -y curl python3-pip && rm -rf /var/lib/apt/lists/*

# Install Python redis client for foreachBatch Redis sink
RUN pip3 install --no-cache-dir redis==5.2.1

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

# Download MinIO/S3 Connectors (Hadoop AWS and AWS SDK)
ENV HADOOP_VERSION=3.3.4
ENV AWS_SDK_VERSION=1.12.262

RUN curl -s https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_VERSION}/hadoop-aws-${HADOOP_VERSION}.jar \
    -o /opt/spark/jars/hadoop-aws-${HADOOP_VERSION}.jar && \
    curl -s https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar \
    -o /opt/spark/jars/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar

# Download PostgreSQL JDBC Driver (for Iceberg JDBC catalog → iceberg_catalog DB)
ENV POSTGRESQL_VERSION=42.7.10

RUN curl -s https://repo1.maven.org/maven2/org/postgresql/postgresql/${POSTGRESQL_VERSION}/postgresql-${POSTGRESQL_VERSION}.jar \
    -o /opt/spark/jars/postgresql-${POSTGRESQL_VERSION}.jar

# Download spark-redis (with bundled dependencies — includes jedis client)
ENV SPARK_REDIS_VERSION=3.1.0

RUN curl -s https://repo1.maven.org/maven2/com/redislabs/spark-redis_${SCALA_VERSION}/${SPARK_REDIS_VERSION}/spark-redis_${SCALA_VERSION}-${SPARK_REDIS_VERSION}-jar-with-dependencies.jar \
    -o /opt/spark/jars/spark-redis_${SCALA_VERSION}-${SPARK_REDIS_VERSION}-jar-with-dependencies.jar

# Download Iceberg AWS bundle (provides S3FileIO with AWS SDK v2 — required for S3FileIO impl)
RUN curl -s https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar \
    -o /opt/spark/jars/iceberg-aws-bundle-${ICEBERG_VERSION}.jar

WORKDIR /opt/spark


USER spark
