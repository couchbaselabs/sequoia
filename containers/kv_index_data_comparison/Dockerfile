# Use an official Python runtime as a parent image
FROM python:3.9

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install any necessary dependencies
RUN pip install couchbase

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY kv_index_data_comparison.py .

# Create an output directory inside the container
RUN mkdir -p /tmp

# Run the Python script as the container's entrypoint
ENTRYPOINT ["python", "kv_index_data_comparison.py"]
