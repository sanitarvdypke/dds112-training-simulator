"""classifier import staging"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0002_classifier_import"
down_revision="0001_initial"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("classifier_imports", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("filename", sa.String(255), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="STAGED"), sa.Column("rows", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("validation_errors", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("created_by", sa.UUID(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade(): op.drop_table("classifier_imports")
