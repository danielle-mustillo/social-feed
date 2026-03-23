CREATE KEYSPACE IF NOT EXISTS social_feed
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE social_feed;

CREATE TABLE IF NOT EXISTS users (
  user_id uuid PRIMARY KEY,
  username text,
  deleted_at timestamp
);

CREATE TABLE IF NOT EXISTS followers_by_user (
  user_id uuid,
  follower_id uuid,
  followed_at timestamp,
  PRIMARY KEY ((user_id), follower_id)
);

CREATE TABLE IF NOT EXISTS posts_by_user (
  user_id uuid,
  post_time timeuuid,
  post_id uuid,
  body text,
  PRIMARY KEY ((user_id), post_time)
) WITH CLUSTERING ORDER BY (post_time DESC);

CREATE TABLE IF NOT EXISTS feed_by_user (
  user_id uuid,
  event_time timeuuid,
  actor_id uuid,
  post_id uuid,
  body text,
  PRIMARY KEY ((user_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
