# Cassandra Social Feed on Kind with MetalLB

This repository contains a minimal social feed API that demonstrates Cassandra as a query-driven, append-optimized database. The stack is designed to run locally inside a `kind` Kubernetes cluster running on one physical machine: a 7-node local Kubernetes cluster (`1` control-plane, `6` workers), a six-node Cassandra ring modeled as two datacenters with three racks each, one FastAPI app, schema bootstrap via a Kubernetes Job, MetalLB for `LoadBalancer` IP allocation, and ingress-nginx for HTTP routing.

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

## Soft Delete Behavior

User deletion is implemented as a soft delete rather than a synchronous multi-table cleanup.

- the `users` row gets a `deleted_at` timestamp
- deleted users no longer appear in normal user reads
- deleted users cannot create posts or follows
- follower lists filter out deleted followers
- feed reads filter out items whose `actor_id` now points at a deleted user

This keeps writes simple and avoids a cross-table delete workflow in the request path. Old denormalized rows may still exist in Cassandra, but the API stops serving them.

## Cassandra Tracing

The app can optionally log Cassandra query traces for every repository-backed endpoint. This is not a relational `EXPLAIN` plan. Instead, it uses Cassandra request tracing and logs which coordinator handled the query plus the recorded trace events.

Available env vars:

- `CASSANDRA_TRACE_ENABLED=true|false`
- `CASSANDRA_TRACE_SAMPLE_RATE=0.0-1.0`
- `CASSANDRA_TRACE_LOG_EVENTS=true|false`
- `CASSANDRA_TRACE_MAX_WAIT_SECONDS=5`

When enabled, the app logs:

- one HTTP request log line with `request_id`, method, path, status, and whether Cassandra tracing was on
- one Cassandra trace log line per repository query
- optional trace event lines if `CASSANDRA_TRACE_LOG_EVENTS=true`

The deployment manifest currently enables tracing in [app.yaml](/home/DanielleMustillo/test/social-feed/k8s/app.yaml). Because the local cluster now runs six Cassandra nodes across two logical datacenters, the `coordinator` field is useful for demonstrating how the driver routes requests around the ring.

## Limitations

- The service duplicates post content into follower feeds.
- Popular accounts create the classic Cassandra "celebrity problem" because one post can fan out to many followers.
- The demo uses a six-node Cassandra ring for local development, but it is still not production-grade.
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

### Soft-delete a user

```http
DELETE /users/{user_id}
```

This marks the user deleted. It does not synchronously remove every follower, post, or feed row from Cassandra.

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
- `tests/`: bash demo script for exercising the live API

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

This creates the kind cluster, installs MetalLB, installs ingress-nginx, starts a six-node Cassandra ring, initializes the schema, and deploys the API.

The `kind` cluster itself is now multi-node, but all of those Kubernetes nodes are still Docker containers on this same machine. Cassandra is pinned to the 6 worker nodes and modeled as:

- `dc1/rack1`, `dc1/rack2`, `dc1/rack3`
- `dc2/rack1`, `dc2/rack2`, `dc2/rack3`

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

If you are upgrading an existing install to the 2-datacenter, 6-rack topology, rebuild the data plane with:

```bash
make clean
make up
```

### 4. Verify the deployment

Check the workload state:

```bash
kubectl get nodes
kubectl get pods -n social-feed
kubectl get pods -n social-feed -o wide
kubectl get ingress -n social-feed
kubectl logs job/social-feed-schema-init -n social-feed
kubectl get svc -n ingress-nginx ingress-nginx-controller
kubectl exec -n social-feed cassandra-dc1-rack1-0 -- nodetool status
```

Then call the health endpoint:

```bash
curl http://social-feed.local/healthz
```

If you do not want to edit host resolution, you can still call the ingress IP directly:

```bash
curl http://<INGRESS_IP>/healthz -H 'Host: social-feed.local'
```

Run the bash demo script against the live ingress:

```bash
make test
```

To show multi-node Cassandra behavior directly, compare the ring view and the coordinator fields in the app logs:

```bash
kubectl exec -n social-feed cassandra-dc1-rack1-0 -- nodetool status
kubectl logs -n social-feed deployment/social-feed-api --tail=200 | grep cassandra_trace
```

`nodetool status` should show three `UN` nodes in `dc1` and three `UN` nodes in `dc2`, with racks `rack1`, `rack2`, and `rack3` in each datacenter. The trace logs include `coordinator=<pod-ip>` values that identify which Cassandra node coordinated each request.

`kubectl get nodes` should show one control-plane node and six worker nodes for the local kind cluster. `kubectl get pods -n social-feed -o wide` lets you see which Kubernetes node each Cassandra pod landed on.

This resolves the current ingress `LoadBalancer` IP and runs [smoke_live.sh](/home/DanielleMustillo/test/social-feed/tests/smoke_live.sh) with the correct base URL and `Host` header.

If you want a direct shell smoke test, run:

```bash
tests/smoke_live.sh
```

It resets the app, creates Alice/Bob/Carol, adds follow relationships, creates posts, and prints the resulting profile/feed responses with `curl` and `jq`. You can override the target with `SOCIAL_FEED_BASE_URL` and `SOCIAL_FEED_HOST_HEADER`.

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

## Demo Script

The repo keeps a single shell-based demo script in [smoke_live.sh](/home/DanielleMustillo/test/social-feed/tests/smoke_live.sh). It is meant for manual showcasing rather than Python-based automated testing.
