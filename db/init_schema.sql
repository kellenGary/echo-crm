-- ============================================================================
-- Echo CRM — PostgreSQL Schema Initialization
-- ============================================================================
-- Run once against a fresh database:
--   psql -d echo_crm -f init_schema.sql
--
-- Prerequisites:
--   CREATE DATABASE echo_crm;
-- ============================================================================

-- Required extensions --------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "vector";      -- pgvector for embeddings

-- 1. contacts ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    display_name    VARCHAR(255) NOT NULL,
    unstructured_profile  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. linked_accounts ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS linked_accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contact_id      UUID NOT NULL
                        REFERENCES contacts(id) ON DELETE CASCADE,
    provider        VARCHAR(64) NOT NULL,
    provider_id     VARCHAR(255) NOT NULL,
    username_handle VARCHAR(255),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT uq_linked_accounts_provider_id
        UNIQUE (provider, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_linked_accounts_contact_id
    ON linked_accounts (contact_id);

-- 3. relationships -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS relationships (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contact_id_1        UUID NOT NULL
                            REFERENCES contacts(id) ON DELETE CASCADE,
    contact_id_2        UUID NOT NULL
                            REFERENCES contacts(id) ON DELETE CASCADE,
    relationship_type   VARCHAR(64) NOT NULL,
    confidence_score    DOUBLE PRECISION CHECK (confidence_score BETWEEN 0.0 AND 1.0),

    CONSTRAINT uq_relationships_pair_type
        UNIQUE (contact_id_1, contact_id_2, relationship_type),

    -- Prevent self-referencing relationships
    CONSTRAINT chk_no_self_relationship
        CHECK (contact_id_1 <> contact_id_2)
);

CREATE INDEX IF NOT EXISTS idx_relationships_contact_1
    ON relationships (contact_id_1);

CREATE INDEX IF NOT EXISTS idx_relationships_contact_2
    ON relationships (contact_id_2);

-- 4. messages ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_message_id VARCHAR(512),
    provider            VARCHAR(64) NOT NULL,
    sender_provider_id  VARCHAR(255) NOT NULL,
    content             TEXT,
    timestamp           TIMESTAMPTZ,
    is_extracted        BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_messages_provider_msg
        UNIQUE (provider, provider_message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_provider_sender
    ON messages (provider, sender_provider_id);

CREATE INDEX IF NOT EXISTS idx_messages_is_extracted
    ON messages (is_extracted)
    WHERE is_extracted = FALSE;          -- partial index: only un-extracted rows

-- 5. extracted_facts ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS extracted_facts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    summary             TEXT NOT NULL,
    embedding           vector(768),       -- dimension must match your model
    source_message_ids  UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Approximate nearest-neighbor index (IVFFlat).
-- Tune `lists` when the table grows (rule of thumb: sqrt(row_count)).
CREATE INDEX IF NOT EXISTS idx_extracted_facts_embedding
    ON extracted_facts
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 6. contact_facts (many-to-many join) ---------------------------------------
CREATE TABLE IF NOT EXISTS contact_facts (
    contact_id  UUID NOT NULL
                    REFERENCES contacts(id) ON DELETE CASCADE,
    fact_id     UUID NOT NULL
                    REFERENCES extracted_facts(id) ON DELETE CASCADE,
    role        VARCHAR(128),

    PRIMARY KEY (contact_id, fact_id)
);

CREATE INDEX IF NOT EXISTS idx_contact_facts_fact_id
    ON contact_facts (fact_id);
