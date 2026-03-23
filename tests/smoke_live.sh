#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SOCIAL_FEED_BASE_URL:-http://social-feed.local}"
HOST_HEADER="${SOCIAL_FEED_HOST_HEADER:-social-feed.local}"

echo "Base URL: ${BASE_URL}"
echo

echo "Resetting demo data..."
curl -sS -X POST -H "Host: ${HOST_HEADER}" "${BASE_URL}/admin/reset" | jq
echo

echo "Creating Alice, Bob, and Carol..."
ALICE_ID="$(curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/users" -d '{"username":"alice"}' | jq -r '.user_id')"
BOB_ID="$(curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/users" -d '{"username":"bob"}' | jq -r '.user_id')"
CAROL_ID="$(curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/users" -d '{"username":"carol"}' | jq -r '.user_id')"

echo "Alice: ${ALICE_ID}"
echo "Bob:   ${BOB_ID}"
echo "Carol: ${CAROL_ID}"
echo

echo "Bob follows Alice..."
curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/follow" -d "{\"follower_id\":\"${BOB_ID}\",\"followed_id\":\"${ALICE_ID}\"}" | jq
echo

echo "Carol follows Alice..."
curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/follow" -d "{\"follower_id\":\"${CAROL_ID}\",\"followed_id\":\"${ALICE_ID}\"}" | jq
echo

echo "Alice creates two posts..."
curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/posts" -d "{\"user_id\":\"${ALICE_ID}\",\"body\":\"Hello world\"}" | jq
curl -sS -X POST -H "Content-Type: application/json" -H "Host: ${HOST_HEADER}" "${BASE_URL}/posts" -d "{\"user_id\":\"${ALICE_ID}\",\"body\":\"Second post\"}" | jq
echo

echo "All users:"
curl -sS -H "Host: ${HOST_HEADER}" "${BASE_URL}/users" | jq
echo

echo "Alice's profile posts:"
curl -sS -H "Host: ${HOST_HEADER}" "${BASE_URL}/users/${ALICE_ID}/posts?limit=50" | jq
echo

echo "Bob's home feed:"
curl -sS -H "Host: ${HOST_HEADER}" "${BASE_URL}/users/${BOB_ID}/feed?limit=50" | jq
echo

echo "Carol's home feed:"
curl -sS -H "Host: ${HOST_HEADER}" "${BASE_URL}/users/${CAROL_ID}/feed?limit=50" | jq
echo

echo "Done."
