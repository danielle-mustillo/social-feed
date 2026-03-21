# Cassandra Social Feed Demo

## Overview

Build a minimal social feed service that demonstrates how to use **Cassandra as a query-driven, append-optimized database**.

The system supports:

* creating users
* following other users
* posting short messages
* viewing a user’s own posts (profile timeline)
* viewing a precomputed home feed

The goal is NOT feature completeness.

The goal is to clearly demonstrate:

* partition keys vs clustering keys
* denormalized data modeling
* fanout-on-write
* time-ordered queries
* bounded partitions (optional stretch)

---

## Tech Stack

* Backend: Python (FastAPI)
* Database: Apache Cassandra (via Docker)
* Cassandra client: `cassandra-driver`
* No frontend required (optional minimal HTML or curl examples)

---

## Core Concepts to Demonstrate

This project should explicitly showcase:

1. **Query-first data modeling**

   * Tables are designed around queries, not normalization

2. **Wide-row storage**

   * Each user’s feed is a partition

3. **Append-only writes**

   * New events are inserted, not updated

4. **Fanout-on-write**

   * A post is written to all followers’ feeds

5. **Time-ordered reads**

   * Clustering key enforces ordering

---

## Data Model (Cassandra Schema)

### Users

```sql
CREATE TABLE users (
  user_id uuid PRIMARY KEY,
  username text
);
```

---

### Followers (who follows a user)

```sql
CREATE TABLE followers_by_user (
  user_id uuid,
  follower_id uuid,
  followed_at timestamp,
  PRIMARY KEY ((user_id), follower_id)
);
```

Query supported:

* Get all followers of a user

---

### Posts by User (profile timeline)

```sql
CREATE TABLE posts_by_user (
  user_id uuid,
  post_time timeuuid,
  post_id uuid,
  body text,
  PRIMARY KEY ((user_id), post_time)
) WITH CLUSTERING ORDER BY (post_time DESC);
```

Query supported:

* Get latest posts by a user

---

### Feed by User (home feed)

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

Query supported:

* Get latest feed items for a user

---

## API Endpoints

### Create User

```
POST /users
{
  "username": "alice"
}
```

---

### Follow User

```
POST /follow
{
  "follower_id": "...",
  "followed_id": "..."
}
```

---

### Create Post

```
POST /posts
{
  "user_id": "...",
  "body": "Hello world"
}
```

Behavior:

1. Insert into `posts_by_user`
2. Fetch followers of the author
3. For each follower:

   * insert into `feed_by_user`

This is **fanout-on-write**

---

### Get User Posts (Profile)

```
GET /users/{user_id}/posts?limit=50
```

Reads from:

* `posts_by_user`

---

### Get User Feed

```
GET /users/{user_id}/feed?limit=50
```

Reads from:

* `feed_by_user`

---

## Project Structure

```
app/
  main.py
  cassandra.py
  models.py

  routes/
    users.py
    follow.py
    posts.py
    feed.py

  services/
    fanout.py

schema.cql
docker-compose.yml
README.md
```

---

## Cassandra Setup (Docker)

Use a single-node Cassandra for simplicity.

Example docker-compose service:

* cassandra:latest
* expose port 9042

App should wait until Cassandra is ready before connecting.

---

## Fanout Logic (Important)

When a user creates a post:

1. Insert post into `posts_by_user`
2. Query `followers_by_user` for that user
3. For each follower:

   * insert a feed row into `feed_by_user`

This should be implemented in a service layer (e.g. `fanout.py`)

Batching is optional but encouraged.

---

## Demo Flow (Must Work)

1. Create users: Alice, Bob, Carol
2. Bob follows Alice
3. Carol follows Alice
4. Alice creates a post
5. Fetch Alice’s posts → should contain the post
6. Fetch Bob’s feed → should contain Alice’s post
7. Fetch Carol’s feed → should contain Alice’s post

---

## Stretch Goals (Optional)

### 1. Time Bucketing (Important Cassandra concept)

Prevent unbounded partitions:

```sql
PRIMARY KEY ((user_id, day), event_time)
```

---

### 2. Pagination

Use `timeuuid` to paginate older results.

---

### 3. Async Fanout

Simulate queue-based fanout (even in-memory)

---

### 4. Idempotency

Avoid duplicate inserts during retries

---

## Non-Goals

Do NOT implement:

* authentication
* real-time updates (websockets)
* likes/comments
* full frontend
* complex ranking

---

## README Requirements

README should explain:

1. Why Cassandra was chosen
2. Each table and its query
3. Partition key vs clustering key
4. Fanout-on-write tradeoffs
5. Limitations (celebrity problem, duplication)

---

## Success Criteria

The project is successful if:

* API works end-to-end
* Cassandra schema matches query patterns
* Fanout-on-write is implemented correctly
* Feed reads are a single-partition query
* README explains design clearly

---

## Key Insight

This system models:

> “Each user’s feed as a partition containing a time-ordered sequence of immutable events.”

This is the core idea behind using Cassandra for feeds.

---

