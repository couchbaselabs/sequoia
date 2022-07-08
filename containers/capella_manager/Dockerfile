FROM python:3.7
RUN git clone https://github.com/couchbaselabs/CapellaRESTAPIs
WORKDIR "/CapellaRESTAPIs"
RUN git checkout -b addingParams
RUN git pull origin addingParams
RUN git log
RUN python setup.py install
RUN pip install requests
COPY capella_api_manager.py /CapellaRESTAPIs/
COPY cluster_config.json /CapellaRESTAPIs/
COPY cluster_config_ami.json /CapellaRESTAPIs/

RUN touch /tmp/provider_temp.yml
ENTRYPOINT ["python3", "capella_api_manager.py"]
