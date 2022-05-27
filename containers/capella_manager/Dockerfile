FROM python:3.7
RUN git clone https://github.com/pavan-couchbase/CapellaRESTAPIs
WORKDIR "/CapellaRESTAPIs"
RUN python setup.py install
RUN pip install requests
COPY capella_api_manager.py /CapellaRESTAPIs/
COPY cluster_config.json /CapellaRESTAPIs/
RUN touch /tmp/provider_temp.yml
ENTRYPOINT ["python3", "capella_api_manager.py"]
