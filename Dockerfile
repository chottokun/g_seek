# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the project files
COPY . /app

# Install the project's dependencies
RUN uv sync --frozen --no-dev

# Place executable scripts in the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose Streamlit and Chainlit ports
EXPOSE 8501
EXPOSE 8000

# Default command to run the application
# We use chainlit as the default, but it can be overridden
CMD ["/app/.venv/bin/python", "-m", "chainlit", "run", "deep_research_project/chainlit_app.py", "--host", "0.0.0.0", "--port", "8000"]
