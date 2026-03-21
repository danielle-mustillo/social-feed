# Cassandra Social Feed on Kind with MetalLB

This repository contains a minimal social feed API that demonstrates Cassandra as a query-driven, append-optimized database. The stack is designed to run locally inside a `kind` Kubernetes cluster: one Cassandra node, one FastAPI app, schema bootstrap via a Kubernetes Job, MetalLB for `LoadBalancer` IP allocation, and ingress-nginx for HTTP routing.

## Why Cassandra

This demo is intentionally centered on the data model rather than feature breadth. Cassandra is a good fit here because the core read paths are narrow, predictable, and ordered by time:

- fetch the latest posts for one user
- fetch the latest home-feed items for one user
- fetch the followers of one author during fanout

Those access patterns map naturally to Cassandra partitions and clustering columns. Instead of normalizing data and joining it later, the service writes denormalized rows that make each read path a single-partition query.

## Data Model and Queries

### `users`

Stores the canonical user identifier and username.

```sql
CREATE TABLE users (
  user_id uuid PRIMARY KEY,
  username text
);
```

Supported query:

- look up whether a user exists by `user_id`

### `followers_by_user`

Stores follower relationships partitioned by the followed user.

```sql
CREATE TABLE followers_by_user (
  user_id uuid,
  follower_id uuid,
  followed_at timestamp,
  PRIMARY KEY ((user_id), follower_id)
);
```

Supported query:

- get all followers of a user during fanout

### `posts_by_user`

Stores a user’s profile timeline as a time-ordered wide row.

```sql
CREATE TABLE posts_by_user (
  user_id uuid,
  post_time timeuuid,
  post_id uuid,
  body text,
  PRIMARY KEY ((user_id), post_time)
) WITH CLUSTERING ORDER BY (post_time DESC);
```

Supported query:

- get the newest posts for one user

### `feed_by_user`

Stores each user’s precomputed home feed as immutable events.

```sql
CREATE TABLE feed_by_user (
  user_id uuid,
  event_time timeuuid,
  actor_id uuid,
  post_id uuid,
  body text,
  PRIMARY KEY ((user_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
```

Supported query:

- get the newest feed items for one user

## Partition Key vs Clustering Key

The partition key determines where the data lives and which rows a query can target efficiently.

- In `posts_by_user`, the partition key is `user_id`. One user’s posts live together.
- In `feed_by_user`, the partition key is also `user_id`. One user’s feed is one partition.
- In `followers_by_user`, the partition key is the followed user’s `user_id`, which makes follower lookups efficient during fanout.

The clustering key determines order within a partition.

- `post_time` orders posts newest-first inside a user’s profile partition.
- `event_time` orders feed items newest-first inside a user’s feed partition.

This is the core Cassandra idea the project is trying to highlight: model tables around the exact reads you need.

## Fanout-on-Write

When a user creates a post, the API does three things synchronously:

1. inserts the post into `posts_by_user`
2. reads the author’s followers from `followers_by_user`
3. inserts one feed row into `feed_by_user` for each follower

That makes home-feed reads cheap because they are just a single-partition lookup. The tradeoff is duplicate storage and more expensive writes.

## Limitations

- The service duplicates post content into follower feeds.
- Popular accounts create the classic Cassandra "celebrity problem" because one post can fan out to many followers.
- The demo uses a single Cassandra node for local development only.
- There is no pagination, authentication, ranking, or async fanout in this version.
- Usernames are not unique and follow relationships are idempotent only because the Cassandra primary key overwrites duplicates.

## API

### Create user

```http
POST /users
Content-Type: application/json

{
  "username": "alice"
}
```

### Follow a user

```http
POST /follow
Content-Type: application/json

{
  "follower_id": "2c6d3f77-89dc-4a5d-a6af-349f03de7c6b",
  "followed_id": "f90e4a5d-f4bc-40c7-89cc-7e72a2467d84"
}
```

### Create post

```http
POST /posts
Content-Type: application/json

{
  "user_id": "f90e4a5d-f4bc-40c7-89cc-7e72a2467d84",
  "body": "Hello world"
}
```

### List users

```http
GET /users
```

This endpoint is for demo convenience. In Cassandra it requires scanning the `users` table, so it is not the query-first path the rest of the schema is optimized for.

### Read one user

```http
GET /users/{user_id}
```

### Read followers for a user

```http
GET /follow?followed_id={user_id}
```

### Read profile timeline

```http
GET /users/{user_id}/posts?limit=50
```

### Read profile timeline via top-level route

```http
GET /posts?user_id={user_id}&limit=50
```

### Read home feed

```http
GET /users/{user_id}/feed?limit=50
```

### Read home feed via top-level route

```http
GET /feed?user_id={user_id}&limit=50
```

## Project Layout

- `app/`: FastAPI app, route handlers, fanout service, config, and Cassandra repository
- `schema.cql`: keyspace and tables
- `k8s/`: raw manifests for kind, MetalLB config, Cassandra, schema bootstrap, app deployment, and ingress
- `tests/`: one API-flow test using the in-memory repository and one optional live test for a running cluster

## Local Kind Workflow

### Prerequisites

- Docker
- `kind`
- `kubectl`
- Python 3.12+
- Docker networking that allows the host to reach the `kind` bridge subnet

This repo’s `Makefile` defaults to the current ingress-nginx cloud manifest and MetalLB native manifest as of March 21, 2026:

`https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.14.3/deploy/static/provider/cloud/deploy.yaml`

`https://raw.githubusercontent.com/metallb/metallb/v0.15.3/config/manifests/metallb-native.yaml`

If either upstream version changes, override `INGRESS_NGINX_MANIFEST` or `METALLB_MANIFEST` when you run `make up`.

### 1. Create the cluster and deploy everything

```bash
make up
```

This creates the kind cluster, installs MetalLB, installs ingress-nginx, starts Cassandra, initializes the schema, and deploys the API.

The default MetalLB pool is `172.19.255.200-172.19.255.250`. That assumes the standard Docker `kind` bridge subnet on Linux. If your local Docker network uses a different subnet, update [k8s/metallb-config.yaml](/home/DanielleMustillo/test/social-feed/k8s/metallb-config.yaml) before running `make up`.

### 2. Discover the ingress IP

```bash
make ingress-ip
```

Then map your hostname to that IP:

```text
<INGRESS_IP> social-feed.local
```

### 3. Redeploy only the app after code changes

```bash
make deploy
```

This rebuilds the image, loads it into kind, reapplies the app manifests, and restarts the `social-feed-api` deployment. It does not re-run Cassandra or schema bootstrap.

### 4. Verify the deployment

Check the workload state:

```bash
kubectl get pods -n social-feed
kubectl get ingress -n social-feed
kubectl logs job/social-feed-schema-init -n social-feed
kubectl get svc -n ingress-nginx ingress-nginx-controller
```

Then call the health endpoint:

```bash
curl http://social-feed.local/healthz
```

If you do not want to edit host resolution, you can still call the ingress IP directly:

```bash
curl http://<INGRESS_IP>/healthz -H 'Host: social-feed.local'
```

Run the live integration test without needing local Python test tooling:

```bash
make test-live
```

This builds a small test-runner image from [Dockerfile.test](/home/DanielleMustillo/test/social-feed/Dockerfile.test), targets the current ingress `LoadBalancer` IP, and sends the `Host: social-feed.local` header so ingress routing still matches.

To wipe the demo data from Cassandra through the app and verify the cluster is empty again, run:

```bash
make test-cleanup
```

This calls `POST /admin/reset` and then verifies `GET /users` returns an empty list.

## Demo Flow

With the API reachable, the required demo sequence is:

1. create Alice, Bob, and Carol
2. Bob follows Alice
3. Carol follows Alice
4. Alice creates a post
5. fetch Alice’s posts
6. fetch Bob’s feed
7. fetch Carol’s feed

Example with `curl` and `jq`:

```bash
BASE_URL=http://social-feed.local

ALICE_ID=$(curl -s "$BASE_URL/users" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice"}' | jq -r '.user_id')

BOB_ID=$(curl -s "$BASE_URL/users" \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob"}' | jq -r '.user_id')

CAROL_ID=$(curl -s "$BASE_URL/users" \
  -H 'Content-Type: application/json' \
  -d '{"username":"carol"}' | jq -r '.user_id')

curl -s "$BASE_URL/follow" \
  -H 'Content-Type: application/json' \
  -d "{\"follower_id\":\"$BOB_ID\",\"followed_id\":\"$ALICE_ID\"}"

curl -s "$BASE_URL/follow" \
  -H 'Content-Type: application/json' \
  -d "{\"follower_id\":\"$CAROL_ID\",\"followed_id\":\"$ALICE_ID\"}"

curl -s "$BASE_URL/posts" \
  -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$ALICE_ID\",\"body\":\"Hello world\"}"

curl -s "$BASE_URL/users/$ALICE_ID/posts?limit=50"
curl -s "$BASE_URL/users/$BOB_ID/feed?limit=50"
curl -s "$BASE_URL/users/$CAROL_ID/feed?limit=50"
```

## Tests

Run the fast API-behavior test locally:

```bash
pytest tests/test_demo_flow.py
```

Run the live cluster test against any reachable deployment URL:

```bash
SOCIAL_FEED_BASE_URL=http://social-feed.local pytest -m live tests/test_live_demo_flow.py
```
