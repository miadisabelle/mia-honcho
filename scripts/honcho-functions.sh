# shellcheck shell=bash
# Honcho shell helpers: list workspaces, peers, sessions, and chat with a peer.
#
#   source scripts/honcho-functions.sh
#   hworkspaces                       # list workspaces
#   hws medicine-wheel                # set current workspace (no arg: show it)
#   hpeers                            # list peers in current workspace
#   hpeer william                     # set current peer (no arg: show it)
#   hsessions [peer]                  # sessions in workspace, or of one peer
#   hcard [peer] [target]             # peer card
#   hchat "What do you remember?"     # ask the current peer
#   hchat -w ws -p peer -l medium -s session -t target "question"
#   hchat                             # interactive loop, empty line or ^D exits
#
# Peer ids are case-sensitive. hchat refuses a peer that does not exist,
# because the chat endpoint would otherwise create it empty and answer
# "no information".
#
# Environment (all optional):
#   HONCHO_URL        default https://honcho.tail3b11eb.ts.net (local: http://127.0.0.1:8133)
#   HONCHO_WORKSPACE  default medicine-wheel
#   HONCHO_PEER       default William
#   HONCHO_REASONING  minimal|low|medium|high|max, default low
#   HONCHO_TOKEN      bearer JWT, only when the server has AUTH_USE_AUTH=true
#
# Requires curl and jq.

: "${HONCHO_URL:=https://honcho.tail3b11eb.ts.net}"
: "${HONCHO_WORKSPACE:=medicine-wheel}"
: "${HONCHO_PEER:=William}"
: "${HONCHO_REASONING:=low}"

# _honcho METHOD PATH [JSON_BODY] -> response body on stdout, non-zero on HTTP error
_honcho() {
  local method=$1 path=$2 body=${3:-} out code
  local -a args=(-sS -X "$method" "${HONCHO_URL%/}/v3$path" -H 'Content-Type: application/json'
    -w '\n%{http_code}')
  [[ -n ${HONCHO_TOKEN:-} ]] && args+=(-H "Authorization: Bearer $HONCHO_TOKEN")
  [[ -n $body ]] && args+=(-d "$body")
  out=$(curl "${args[@]}") || return 1
  code=${out##*$'\n'}
  out=${out%$'\n'*}
  if [[ $code != 2* ]]; then
    printf 'honcho: HTTP %s on %s %s\n%s\n' "$code" "$method" "$path" "$out" >&2
    return 1
  fi
  printf '%s\n' "$out"
}

# _honcho_list PATH [JSON_BODY] -> every item across all pages, one JSON object per line
_honcho_list() {
  local path=$1 body=${2:-'{}'} page=1 pages=1 resp
  while ((page <= pages)); do
    resp=$(_honcho POST "$path?page=$page&size=100" "$body") || return 1
    pages=$(jq -r '.pages // 1' <<<"$resp")
    jq -c '.items[]' <<<"$resp"
    ((page++))
  done
}

hworkspaces() {
  local -
  set -o pipefail
  _honcho_list /workspaces/list |
    jq -r '[.id, .created_at[0:10], (.metadata.purpose // "")] | @tsv'
}

hws() {
  [[ -n ${1:-} ]] && HONCHO_WORKSPACE=$1
  echo "workspace: $HONCHO_WORKSPACE"
}

hpeer() {
  [[ -n ${1:-} ]] && HONCHO_PEER=$1
  echo "peer: $HONCHO_PEER"
}

hpeers() {
  local -
  set -o pipefail
  local ws=${1:-$HONCHO_WORKSPACE}
  _honcho_list "/workspaces/$ws/peers/list" |
    jq -r '[.id, .created_at[0:10], (.metadata | tostring)] | @tsv'
}

hsessions() {
  local -
  set -o pipefail
  local ws=$HONCHO_WORKSPACE path
  if [[ -n ${1:-} ]]; then
    path="/workspaces/$ws/peers/$1/sessions"
  else
    path="/workspaces/$ws/sessions/list"
  fi
  _honcho_list "$path" |
    jq -r '[.id, .created_at[0:10], (if .is_active then "active" else "inactive" end)] | @tsv'
}

hcard() {
  local -
  set -o pipefail
  local peer=${1:-$HONCHO_PEER} target=${2:-} q=''
  [[ -n $target ]] && q="?target=$target"
  _honcho GET "/workspaces/$HONCHO_WORKSPACE/peers/$peer/card$q" |
    jq -r '(.peer_card // ["(no card)"])[]'
}

# _honcho_peer_exists WS PEER -> 0 if the peer exists, message on stderr otherwise
_honcho_peer_exists() {
  local body resp
  body=$(jq -n --arg p "$2" '{filters: {id: $p}}')
  resp=$(_honcho POST "/workspaces/$1/peers/list?size=1" "$body") || return 1
  if [[ $(jq -r '.total' <<<"$resp") == 0 ]]; then
    echo "honcho: no peer '$2' in workspace '$1' (ids are case-sensitive, see hpeers)" >&2
    return 1
  fi
}

# _honcho_ask WS PEER LEVEL SESSION TARGET QUERY
_honcho_ask() {
  local -
  set -o pipefail
  local body
  body=$(jq -n --arg q "$6" --arg l "$3" --arg s "$4" --arg t "$5" \
    '{query: $q, reasoning_level: $l}
     + (if $s != "" then {session_id: $s} else {} end)
     + (if $t != "" then {target: $t} else {} end)')
  _honcho POST "/workspaces/$1/peers/$2/chat" "$body" | jq -r '.content // "(empty answer)"'
}

hchat() {
  local ws=$HONCHO_WORKSPACE peer=$HONCHO_PEER level=$HONCHO_REASONING
  local session='' target='' opt OPTIND=1
  while getopts 'w:p:l:s:t:h' opt; do
    case $opt in
      w) ws=$OPTARG ;;
      p) peer=$OPTARG ;;
      l) level=$OPTARG ;;
      s) session=$OPTARG ;;
      t) target=$OPTARG ;;
      *)
        echo 'usage: hchat [-w workspace] [-p peer] [-l level] [-s session] [-t target] [question]' >&2
        return 2
        ;;
    esac
  done
  shift $((OPTIND - 1))
  _honcho_peer_exists "$ws" "$peer" || return 1

  if (($#)); then
    _honcho_ask "$ws" "$peer" "$level" "$session" "$target" "$*"
    return
  fi

  local line
  echo "chat with $peer in $ws ($level). Empty line or ^D exits."
  while IFS= read -r -e -p "$peer> " line && [[ -n $line ]]; do
    history -s "$line"
    _honcho_ask "$ws" "$peer" "$level" "$session" "$target" "$line"
    echo
  done
}
