TLS files for nginx (Docker bind-mount). They must exist on the host but must NOT be committed to git.

Create fullchain.pem and privkey.pem in this folder:

  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout privkey.pem -out fullchain.pem \
    -subj "/CN=short.urlshortener-mlh.xyz"

Then: docker compose up -d nginx

*.pem is listed in .gitignore and .dockerignore.
