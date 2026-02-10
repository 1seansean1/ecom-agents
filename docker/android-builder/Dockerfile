FROM eclipse-temurin:17-jdk-jammy

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH="${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        unzip wget git && \
    rm -rf /var/lib/apt/lists/*

# Android SDK cmdline-tools
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools && \
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
         -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d ${ANDROID_HOME}/cmdline-tools && \
    mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest && \
    rm /tmp/cmdline-tools.zip

# Accept licenses and install SDK components
RUN yes | sdkmanager --licenses > /dev/null 2>&1 && \
    sdkmanager \
        "platform-tools" \
        "build-tools;34.0.0" \
        "platforms;android-34"

# Gradle 8.5
RUN wget -q https://services.gradle.org/distributions/gradle-8.5-bin.zip \
         -O /tmp/gradle.zip && \
    unzip -q /tmp/gradle.zip -d /opt && \
    ln -s /opt/gradle-8.5/bin/gradle /usr/local/bin/gradle && \
    rm /tmp/gradle.zip

# Workspace
RUN mkdir -p /workspace
WORKDIR /workspace

# Keep container running
CMD ["tail", "-f", "/dev/null"]
