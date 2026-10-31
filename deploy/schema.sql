-- AndYouChat 建表语句（MySQL 8.0 / utf8mb4）
-- 说明：服务启动时会自动执行 Base.metadata.create_all，本文件仅供查阅或手工建库使用。
-- 手工执行前请先建库：CREATE DATABASE andyouchat DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE conversation_members (
	id BIGINT NOT NULL, 
	conversation_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	last_read_seq BIGINT NOT NULL, 
	unread INTEGER NOT NULL, 
	pinned BOOL NOT NULL, 
	muted BOOL NOT NULL, 
	joined_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_member UNIQUE (conversation_id, user_id)
);
CREATE INDEX ix_member_user ON conversation_members (user_id);

CREATE TABLE conversations (
	id BIGINT NOT NULL, 
	type VARCHAR(16) NOT NULL, 
	single_key VARCHAR(64), 
	title VARCHAR(64), 
	seq_counter BIGINT NOT NULL, 
	last_msg_id BIGINT, 
	last_msg_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (single_key)
);

CREATE TABLE friend_requests (
	id BIGINT NOT NULL, 
	from_user_id BIGINT NOT NULL, 
	to_user_id BIGINT NOT NULL, 
	message VARCHAR(128), 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL, 
	handled_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_friend_request_from_status ON friend_requests (from_user_id, status);
CREATE INDEX ix_friend_request_to_status ON friend_requests (to_user_id, status);

CREATE TABLE friendships (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	friend_id BIGINT NOT NULL, 
	remark VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_friendship UNIQUE (user_id, friend_id)
);
CREATE INDEX ix_friendship_user ON friendships (user_id);

CREATE TABLE messages (
	id BIGINT NOT NULL, 
	conversation_id BIGINT NOT NULL, 
	seq BIGINT NOT NULL, 
	sender_id BIGINT NOT NULL, 
	msg_type VARCHAR(16) NOT NULL, 
	content VARCHAR(4096) NOT NULL, 
	extra JSON, 
	client_msg_id VARCHAR(64) NOT NULL, 
	revoked BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_message_seq UNIQUE (conversation_id, seq), 
	CONSTRAINT uq_message_client_id UNIQUE (client_msg_id)
);
CREATE INDEX ix_message_conv_seq ON messages (conversation_id, seq);

CREATE TABLE users (
	id BIGINT NOT NULL, 
	username VARCHAR(32) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	nickname VARCHAR(32) NOT NULL, 
	avatar_url VARCHAR(512), 
	sign VARCHAR(128), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_username ON users (username);
