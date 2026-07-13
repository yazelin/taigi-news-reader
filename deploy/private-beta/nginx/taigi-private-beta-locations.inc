# Include this file only inside the existing HTTPS server for
# ching-tech.ddns.net. Do not include it alongside deploy/lan's location file:
# both intentionally own the same /taigi-tts routes.

# auth_request runs after the pre-access rate/connection modules. This preserves
# abuse limits even for requests rejected by the public identity/Origin gate;
# an early rewrite-phase `if ... return` would bypass those limit modules.
location = /_taigi-private-beta-identity-gate {
    internal;
    access_log off;
    if ($taigi_beta_edge_gate_allowed = 0) { return 403; }
    return 204;
}

location = /taigi-tts/health {
    server_tokens off;
    limit_except GET { deny all; }
    limit_req_status 429;
    limit_conn_status 429;
    limit_req zone=taigi_beta_health burst=3 nodelay;
    limit_conn taigi_beta_connections 6;
    limit_conn taigi_beta_global_connections 24;
    client_max_body_size 1k;
    client_body_timeout 5s;
    access_log off;

    proxy_pass http://taigi_private_beta_backend/health;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Authorization "";
    proxy_set_header Cookie "";
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_hide_header Set-Cookie;
    proxy_cache off;
    proxy_store off;
    proxy_connect_timeout 3s;
    proxy_read_timeout 10s;
    proxy_send_timeout 10s;
    send_timeout 30s;

    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
}

location = /taigi-tts/v1/access {
    server_tokens off;
    limit_except GET OPTIONS { deny all; }
    limit_req_status 429;
    limit_conn_status 429;
    limit_req zone=taigi_beta_access burst=3 nodelay;
    limit_conn taigi_beta_connections 6;
    limit_conn taigi_beta_global_connections 24;
    auth_request /_taigi-private-beta-identity-gate;
    client_max_body_size 1k;
    client_body_timeout 5s;
    access_log off;

    proxy_pass http://taigi_private_beta_backend/v1/access;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;
    proxy_set_header Cookie "";
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_hide_header Set-Cookie;
    proxy_hide_header Access-Control-Allow-Origin;
    proxy_hide_header Access-Control-Allow-Methods;
    proxy_hide_header Access-Control-Allow-Headers;
    proxy_hide_header Access-Control-Allow-Credentials;
    proxy_hide_header Access-Control-Expose-Headers;
    proxy_hide_header Access-Control-Max-Age;
    proxy_hide_header Vary;
    proxy_request_buffering off;
    proxy_cache off;
    proxy_store off;
    proxy_connect_timeout 3s;
    proxy_read_timeout 10s;
    proxy_send_timeout 10s;
    send_timeout 30s;

    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    add_header Access-Control-Allow-Origin $taigi_beta_cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Taigi-Extension-Id" always;
    add_header Access-Control-Expose-Headers "Retry-After, X-RateLimit-Reset, X-RateLimit-Remaining, X-RateLimit-Scope" always;
    add_header Access-Control-Max-Age "600" always;
    add_header Vary "Origin" always;
}

location = /taigi-tts/v1/synthesis-jobs {
    server_tokens off;
    limit_except POST OPTIONS { deny all; }
    limit_req_status 429;
    limit_conn_status 429;
    limit_req zone=taigi_beta_create burst=3 nodelay;
    limit_conn taigi_beta_connections 6;
    limit_conn taigi_beta_global_connections 24;
    auth_request /_taigi-private-beta-identity-gate;
    client_max_body_size 32k;
    client_body_buffer_size 32k;
    client_body_timeout 10s;
    access_log off;

    proxy_pass http://taigi_private_beta_backend/v1/synthesis-jobs;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;
    proxy_set_header Cookie "";
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_hide_header Set-Cookie;
    proxy_hide_header Access-Control-Allow-Origin;
    proxy_hide_header Access-Control-Allow-Methods;
    proxy_hide_header Access-Control-Allow-Headers;
    proxy_hide_header Access-Control-Allow-Credentials;
    proxy_hide_header Access-Control-Expose-Headers;
    proxy_hide_header Access-Control-Max-Age;
    proxy_hide_header Vary;
    proxy_request_buffering off;
    proxy_cache off;
    proxy_store off;
    proxy_connect_timeout 3s;
    proxy_read_timeout 30s;
    proxy_send_timeout 30s;
    send_timeout 30s;
    proxy_buffering off;

    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    add_header Access-Control-Allow-Origin $taigi_beta_cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Taigi-Extension-Id" always;
    add_header Access-Control-Expose-Headers "Retry-After, X-RateLimit-Reset, X-RateLimit-Remaining, X-RateLimit-Scope" always;
    add_header Access-Control-Max-Age "600" always;
    add_header Vary "Origin" always;
}

location ^~ /taigi-tts/v1/synthesis-jobs/ {
    server_tokens off;
    limit_except GET DELETE OPTIONS { deny all; }
    limit_req_status 429;
    limit_conn_status 429;
    limit_req zone=taigi_beta_jobs burst=30 nodelay;
    limit_conn taigi_beta_connections 6;
    limit_conn taigi_beta_global_connections 24;
    auth_request /_taigi-private-beta-identity-gate;
    client_max_body_size 1k;
    client_body_timeout 5s;
    access_log off;

    proxy_pass http://taigi_private_beta_backend/v1/synthesis-jobs/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;
    proxy_set_header Cookie "";
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_hide_header Set-Cookie;
    proxy_hide_header Access-Control-Allow-Origin;
    proxy_hide_header Access-Control-Allow-Methods;
    proxy_hide_header Access-Control-Allow-Headers;
    proxy_hide_header Access-Control-Allow-Credentials;
    proxy_hide_header Access-Control-Expose-Headers;
    proxy_hide_header Access-Control-Max-Age;
    proxy_hide_header Vary;
    proxy_request_buffering off;
    proxy_cache off;
    proxy_store off;
    proxy_connect_timeout 3s;
    proxy_read_timeout 30s;
    proxy_send_timeout 30s;
    send_timeout 30s;
    # Completed responses can contain a large base64 WAV. Stream instead of
    # writing it to nginx proxy temp storage; the app permits one successful
    # terminal GET and then retains only a small DELETE tombstone.
    proxy_buffering off;

    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    add_header Access-Control-Allow-Origin $taigi_beta_cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Taigi-Extension-Id" always;
    add_header Access-Control-Expose-Headers "Retry-After, X-RateLimit-Reset, X-RateLimit-Remaining, X-RateLimit-Scope" always;
    add_header Access-Control-Max-Age "600" always;
    add_header Vary "Origin" always;
}

# The extension uses only async jobs. Keep the long synchronous provider route
# and every other backend route unreachable from the Internet.
location = /taigi-tts/v1/synthesize {
    server_tokens off;
    access_log off;
    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    add_header Access-Control-Allow-Origin $taigi_beta_cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Taigi-Extension-Id" always;
    add_header Access-Control-Expose-Headers "Retry-After, X-RateLimit-Reset, X-RateLimit-Remaining, X-RateLimit-Scope" always;
    add_header Access-Control-Max-Age "600" always;
    add_header Vary "Origin" always;
    return 404;
}

location ^~ /taigi-tts/v1/ {
    server_tokens off;
    access_log off;
    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    add_header Access-Control-Allow-Origin $taigi_beta_cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Taigi-Extension-Id" always;
    add_header Access-Control-Expose-Headers "Retry-After, X-RateLimit-Reset, X-RateLimit-Remaining, X-RateLimit-Scope" always;
    add_header Access-Control-Max-Age "600" always;
    add_header Vary "Origin" always;
    return 404;
}

location ^~ /taigi-tts/ {
    server_tokens off;
    access_log off;
    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    return 404;
}

location = /taigi-tts {
    server_tokens off;
    access_log off;
    add_header Cache-Control "no-store, max-age=0" always;
    add_header Pragma "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
    return 404;
}
