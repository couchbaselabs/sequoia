FROM ubuntu:14.04
RUN sudo apt-get update
RUN sudo apt-get -y install sshpass
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh"]
