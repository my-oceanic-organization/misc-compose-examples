FROM alpine:3.23

RUN apk add --no-cache busybox-extras tini \
    && mkdir -p /www \
    && echo "Hello from very-fast-app" > /www/index.html

EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "echo 'very-fast-app: starting httpd on :3000' && exec busybox-extras httpd -f -v -p 3000 -h /www"]
