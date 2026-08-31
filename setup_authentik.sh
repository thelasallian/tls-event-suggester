#!/bin/bash
# Provision Authentik proxy provider + application for tls-event-suggester
# COPIED from webdesk/setup_authentik.sh — same forward auth pattern
# Run ON THE VPS. Idempotent.
set -euo pipefail
BASE="https://auth.thelasallian.com/api/v3"
EXTERNAL_HOST="https://events.thelasallian.com"
ENV_FILE="/opt/authentik/.env"
TOKEN=$(grep -oE '^AUTHENTIK_BOOTSTRAP_TOKEN=.*' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d ' \r')
api() { curl -sS -H "Authorization: Bearer $TOKEN" -A "Mozilla/5.0" -H "Content-Type: application/json" "$@"; }
api_post() { api -X POST -d "$2" "$BASE$1"; }
FLOWS=$(api "$BASE/flows/instances/")
AUTH_FLOW=$(echo "$FLOWS" | python3 -c "import json,sys;print([f['pk'] for f in json.load(sys.stdin)['results'] if f['slug']=='default-provider-authorization-implicit-consent'][0])")
INV_FLOW=$(echo "$FLOWS" | python3 -c "import json,sys;print([f['pk'] for f in json.load(sys.stdin)['results'] if f['slug']=='default-invalidation-flow'][0])")
MAPS=$(api "$BASE/propertymappings/provider/scope/")
PMS=$(echo "$MAPS" | python3 -c "import json,sys;out=[m['pk'] for m in json.load(sys.stdin)['results'] if m['scope_name'] in ('openid','email','profile')]; print(json.dumps(out))")
CERT=$(api "$BASE/crypto/certificatekeypairs/" | python3 -c "import json,sys;print(json.load(sys.stdin)['results'][0]['pk'])")
echo "== proxy provider (tls-event-suggester) =="
EXISTING_ID=$(api "$BASE/providers/proxy/" | python3 -c "import json,sys; r=[p['pk'] for p in json.load(sys.stdin)['results'] if p['name']=='tls-event-suggester-provider']; print(r[0] if r else '')")
PROVIDER_BODY=$(cat <<EJB
{"name":"tls-event-suggester-provider","authorization_flow":"$AUTH_FLOW","invalidation_flow":"$INV_FLOW","external_host":"$EXTERNAL_HOST","mode":"forward_domain","cookie_domain":"thelasallian.com","access_token_validity":"hours=1","refresh_token_validity":"days=30"}
EJB
)
if [ -n "$EXISTING_ID" ]; then PROVIDER_PK=$EXISTING_ID; api -X PATCH -d "$PROVIDER_BODY" "$BASE/providers/proxy/$PROVIDER_PK/" > /dev/null; echo "provider updated: $PROVIDER_PK"; else PROVIDER_PK=$(api_post "/providers/proxy/" "$PROVIDER_BODY" | python3 -c "import json,sys;print(json.load(sys.stdin)['pk'])"); echo "provider created: $PROVIDER_PK"; fi
echo "== application =="
APP_PK=$(api "$BASE/core/applications/" | python3 -c "import json,sys; r=[a['pk'] for a in json.load(sys.stdin)['results'] if a['slug']=='tls-event-suggester']; print(r[0] if r else '')")
if [ -n "$APP_PK" ]; then echo "application exists: $APP_PK"; else APP_PK=$(api_post "/core/applications/" "{\"name\":\"TLS Event Suggester\",\"slug\":\"tls-event-suggester\",\"provider\":\"$PROVIDER_PK\"}" | python3 -c "import json,sys;print(json.load(sys.stdin)['pk'])"); echo "application created: $APP_PK"; fi
echo "== group binding (web — same as WordPress/WebDesk) =="
GROUP_PK=$(api "$BASE/core/groups/" | python3 -c "import json,sys; r=[g['pk'] for g in json.load(sys.stdin)['results'] if g['name']=='web']; print(r[0] if r else '')")
BINDING_EXISTS=$(api "$BASE/policies/bindings/" | python3 -c "import json,sys; r=[b['pk'] for b in json.load(sys.stdin)['results'] if b.get('target')=='$APP_PK' and b.get('group')=='$GROUP_PK']; print('yes' if r else '')")
if [ "$BINDING_EXISTS" != "yes" ]; then api_post "/policies/bindings/" "{\"target\":\"$APP_PK\",\"group\":\"$GROUP_PK\",\"order\":0}" > /dev/null; echo "binding created"; else echo "binding exists"; fi
echo "== embed provider into Embedded Outpost =="
OUTPOST_PK=$(api "$BASE/outposts/instances/" | python3 -c "import json,sys; r=[o['pk'] for o in json.load(sys.stdin)['results'] if o.get('managed')=='goauthentik.io/outposts/embedded']; print(r[0] if r else '')")
HAS_PROVIDER=$(api "$BASE/outposts/instances/$OUTPOST_PK/" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if '$PROVIDER_PK' in d.get('providers',[]) else '')")
if [ "$HAS_PROVIDER" != "yes" ]; then PROVIDERS=$(api "$BASE/outposts/instances/$OUTPOST_PK/" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin).get('providers',[]) + ['$PROVIDER_PK']))"); api -X PATCH -d "{\"providers\": $PROVIDERS}" "$BASE/outposts/instances/$OUTPOST_PK/" > /dev/null; echo "provider added to embedded outpost"; else echo "provider already in embedded outpost"; fi
echo "Done. Nginx fragment at nginx/tls-event-suggester.conf.part"
