"""Initial schema from db/schema.sql

Revision ID: 0001
Revises:
Create Date: 2026-07-22
"""
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On a fresh install this applies the full schema.
    # On an existing deployment run: alembic stamp 0001
    with open("db/schema.sql") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS search_queries_log CASCADE;
        DROP TABLE IF EXISTS provider_budgets CASCADE;
        DROP TABLE IF EXISTS api_call_log CASCADE;
        DROP TABLE IF EXISTS leads CASCADE;
        DROP TABLE IF EXISTS feedback CASCADE;
        DROP TABLE IF EXISTS evaluations CASCADE;
        DROP TABLE IF EXISTS do_not_contact CASCADE;
        DROP TABLE IF EXISTS candidates CASCADE;
        DROP TABLE IF EXISTS malware_signatures CASCADE;
        DROP TABLE IF EXISTS icp_config CASCADE;
        DROP TABLE IF EXISTS campaigns CASCADE;
    """)
