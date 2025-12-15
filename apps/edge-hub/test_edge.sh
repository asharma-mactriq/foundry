#!/bin/bash

BASE="http://localhost:5001"

echo "------------------------------------------"
echo " 1) PING SERVER"
echo "------------------------------------------"
curl -s "$BASE/modes/" | jq .
echo


echo "------------------------------------------"
echo " 2) SET MODE → AUTO"
echo "------------------------------------------"
curl -s -X POST "$BASE/modes/operation/auto" | jq .
echo


echo "------------------------------------------"
echo " 3) SET PROCESS → DISPENSING"
echo "------------------------------------------"
curl -s -X POST "$BASE/modes/process/dispensing" | jq .
echo


echo "------------------------------------------"
echo " 4) LIST COMMAND REGISTRY"
echo "------------------------------------------"
curl -s "$BASE/commands/registry" | jq .
echo


echo "------------------------------------------"
echo " 5) DISPATCH COMMAND → dispense.open(open_ms=400)"
echo "------------------------------------------"
DISPATCH_RESPONSE=$(curl -s -X POST "$BASE/commands/dispatch" \
  -H "Content-Type: application/json" \
  -d '{"name":"dispense.open","payload":{"open_ms":400}}')

echo "$DISPATCH_RESPONSE" | jq .

CMD_ID=$(echo "$DISPATCH_RESPONSE" | jq -r '.cmd_id')

echo
echo "Command ID = $CMD_ID"
echo


echo "------------------------------------------"
echo " 6) POLL COMMAND STORE FOR STATUS"
echo "------------------------------------------"
curl -s "$BASE/command/status/$CMD_ID" | jq .
echo


echo "------------------------------------------"
echo " 7) EMERGENCY STOP TEST"
echo "------------------------------------------"
curl -s -X POST "$BASE/command/dispatch" \
  -H "Content-Type: application/json" \
  -d '{"name":"system.emergency_stop","payload":{}}' | jq .
echo

echo "------------------------------------------"
echo "DONE"
echo "------------------------------------------"
