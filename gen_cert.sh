#!/usr/bin/env bash

if [[ ! -f internal.crt ]] || [[ ! -f internal.key ]]; then
    openssl req -new \
        -newkey rsa:2048 \
        -days 365 \
        -nodes \
        -x509 \
        -keyout internal.key \
        -out internal.crt \
        -subj '/CN=localhost'
fi
