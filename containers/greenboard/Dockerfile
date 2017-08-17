FROM google/nodejs
RUN git clone https://github.com/couchbaselabs/greenboard.git
WORKDIR greenboard
RUN npm install
RUN npm install -g bower
WORKDIR app
RUN git pull
RUN npm install
RUN bower install  -F  --allow-root
RUN npm install grunt-cli grunt-contrib-concat grunt-contrib-uglify
RUN ./node_modules/.bin/grunt 
WORKDIR ../
COPY start.sh start.sh
EXPOSE 8200
ENTRYPOINT ["./start.sh"]
