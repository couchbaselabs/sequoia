FROM ansible/ubuntu14.04-ansible 
RUN apt-get install -y sshpass
RUN mkdir /etc/ansible/group_vars
COPY hosts /etc/ansible/hosts
COPY vars /etc/ansible/group_vars/all
COPY install.yml /install.yml
COPY provision.yml /provision.yml
ENV  ANSIBLE_HOST_KEY_CHECKING False
