FROM python:3.7
RUN git clone https://github.com/couchbaselabs/CapellaRESTAPIs
WORKDIR "/CapellaRESTAPIs"
RUN pip install requests
RUN pip install git+https://github.com/couchbaselabs/CapellaRESTAPIs.git@master
COPY capella_api_manager.py /CapellaRESTAPIs/
COPY cluster_config.json /CapellaRESTAPIs/
COPY cluster_config_ami.json /CapellaRESTAPIs/
RUN touch /tmp/provider_temp.yml
RUN chmod 777 /tmp/provider_temp.yml
ENTRYPOINT ["python3", "capella_api_manager.py"]