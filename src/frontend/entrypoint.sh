#!/usr/bin/env sh
set -e
# Replace placeholders in env-config.template.js with environment variables
if [ -f /usr/share/nginx/html/env-config.template.js ]; then
  tpl=/usr/share/nginx/html/env-config.template.js
  out=/usr/share/nginx/html/env-config.js
  echo "Generating runtime config into ${out}"
  cp "$tpl" "$out"
  for var in $(cat "$tpl" | grep -oE '\{\{[A-Z0-9_]+\}\}' | sed 's/[{}]//g' | sort -u); do
    name=$(echo $var | tr -d \{\})
    val="${!name}"
    if [ -z "$val" ]; then
      val=""
    fi
    sed -i "s/{{${name}}}/${val}/g" "$out"
  done
fi
exec nginx -g 'daemon off;'
