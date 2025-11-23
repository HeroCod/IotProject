FROM contiker/contiki-ng:latest

ARG INSTALL_TOOLS

RUN git clone --recurse-submodules --branch release/v5.0 https://github.com/contiki-ng/contiki-ng.git /home/user/contiki-ng

RUN apt update && apt install -y \
    python3 iptables

# COPY ./install_docker.sh /home/user/install_docker.sh
# RUN chmod +x /home/user/install_docker.sh && /home/user/install_docker.sh && rm /home/user/install_docker.sh

RUN cd /home/user/contiki-ng/tools/serial-io && make tunslip6
