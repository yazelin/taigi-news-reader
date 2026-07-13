# Include these locations inside the existing TLS `server` for a hostname whose
# certificate is trusted by Chrome. This example exposes the base URL
# https://<trusted-hostname>/taigi-tts. nginx reaches the backend only through
# the dedicated taigi_news_reader_edge network; the backend publishes no host
# port. Keep this file's .inc suffix so conf.d/*.conf does not load locations
# at the http context by mistake.

location = /taigi-tts/health {
    allow 127.0.0.1;
    allow 192.168.11.0/24;
    deny all;

    limit_req zone=taigi_health burst=10 nodelay;
    limit_conn taigi_connections 8;
    proxy_pass http://taigi_backend/health;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_connect_timeout 3s;
    proxy_read_timeout 10s;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
}

location = /taigi-tts/v1/access {
    allow 127.0.0.1;
    allow 192.168.11.0/24;
    deny all;
    if ($taigi_extension_request_allowed = 0) { return 403; }

    limit_req zone=taigi_access burst=5 nodelay;
    limit_conn taigi_connections 8;
    client_max_body_size 1k;
    access_log off;
    proxy_pass http://taigi_backend/v1/access;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_connect_timeout 3s;
    proxy_read_timeout 10s;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
}

location = /taigi-tts/v1/synthesis-jobs {
    allow 127.0.0.1;
    allow 192.168.11.0/24;
    deny all;
    if ($taigi_extension_request_allowed = 0) { return 403; }

    limit_req zone=taigi_create burst=4 nodelay;
    limit_conn taigi_connections 8;
    client_max_body_size 32k;
    access_log off;
    proxy_pass http://taigi_backend/v1/synthesis-jobs;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_connect_timeout 3s;
    proxy_read_timeout 30s;
    proxy_buffering off;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
}

location ^~ /taigi-tts/v1/synthesis-jobs/ {
    allow 127.0.0.1;
    allow 192.168.11.0/24;
    deny all;
    if ($taigi_extension_request_allowed = 0) { return 403; }

    limit_req zone=taigi_jobs burst=60 nodelay;
    limit_conn taigi_connections 8;
    client_max_body_size 1k;
    access_log off;
    proxy_pass http://taigi_backend/v1/synthesis-jobs/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_connect_timeout 3s;
    proxy_read_timeout 30s;
    # A completed GET can contain a large base64 WAV. Do not spill it into
    # nginx proxy temp files; stream it directly to the extension.
    proxy_buffering off;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
}

# The Chrome path uses asynchronous jobs. Do not expose the retained long POST.
location = /taigi-tts/v1/synthesize {
    return 404;
}

location ^~ /taigi-tts/ {
    return 404;
}
