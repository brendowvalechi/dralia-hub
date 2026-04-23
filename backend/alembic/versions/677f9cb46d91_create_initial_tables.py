"""create initial tables

Revision ID: 677f9cb46d91
Revises:
Create Date: 2026-04-08 21:35:49.043550

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '677f9cb46d91'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('instances',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('phone_number', sa.String(length=20), nullable=True),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('evolution_instance_name', sa.String(length=255), nullable=False),
    sa.Column('status', sa.Enum('connected', 'disconnected', 'warming_up', 'banned', 'quarantine', name='instancestatus'), nullable=False),
    sa.Column('health_score', sa.Integer(), nullable=False),
    sa.Column('daily_limit', sa.Integer(), nullable=False),
    sa.Column('daily_sent', sa.Integer(), nullable=False),
    sa.Column('warmup_day', sa.Integer(), nullable=True),
    sa.Column('ban_count', sa.Integer(), nullable=False),
    sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_disconnected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('evolution_instance_name')
    )
    op.create_index(op.f('ix_instances_status'), 'instances', ['status'], unique=False)
    op.create_table('leads',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source', sa.Enum('import_', 'manual', 'api', 'webhook', name='leadsource'), nullable=False),
    sa.Column('status', sa.Enum('active', 'inactive', 'opted_out', 'blacklisted', name='leadstatus'), nullable=False),
    sa.Column('opt_in_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('opt_out_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('consent_record', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_leads_phone'), 'leads', ['phone'], unique=True)
    op.create_index(op.f('ix_leads_status'), 'leads', ['status'], unique=False)
    op.create_index('ix_leads_tags', 'leads', ['tags'], unique=False, postgresql_using='gin')
    op.create_table('segments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('lead_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('role', sa.Enum('admin', 'operator', 'viewer', name='userrole'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('campaigns',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('segment_id', sa.UUID(), nullable=True),
    sa.Column('message_template', sa.Text(), nullable=False),
    sa.Column('media_url', sa.String(length=500), nullable=True),
    sa.Column('media_type', sa.Enum('image', 'video', 'audio', 'document', name='mediatype'), nullable=True),
    sa.Column('status', sa.Enum('draft', 'scheduled', 'running', 'paused', 'completed', 'failed', name='campaignstatus'), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('total_leads', sa.Integer(), nullable=False),
    sa.Column('sent_count', sa.Integer(), nullable=False),
    sa.Column('delivered_count', sa.Integer(), nullable=False),
    sa.Column('read_count', sa.Integer(), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['segment_id'], ['segments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_campaigns_status'), 'campaigns', ['status'], unique=False)
    op.create_index(op.f('ix_campaigns_user_id'), 'campaigns', ['user_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('instance_id', sa.UUID(), nullable=True),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('media_url', sa.String(length=500), nullable=True),
    sa.Column('status', sa.Enum('queued', 'sending', 'sent', 'delivered', 'read', 'failed', name='messagestatus'), nullable=False),
    sa.Column('failure_reason', sa.String(length=500), nullable=True),
    sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['instance_id'], ['instances.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_campaign_id'), 'messages', ['campaign_id'], unique=False)
    op.create_index('ix_messages_campaign_status', 'messages', ['campaign_id', 'status'], unique=False)
    op.create_index(op.f('ix_messages_lead_id'), 'messages', ['lead_id'], unique=False)
    op.create_index('ix_messages_sent_at', 'messages', ['sent_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_messages_sent_at', table_name='messages')
    op.drop_index(op.f('ix_messages_lead_id'), table_name='messages')
    op.drop_index('ix_messages_campaign_status', table_name='messages')
    op.drop_index(op.f('ix_messages_campaign_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_campaigns_user_id'), table_name='campaigns')
    op.drop_index(op.f('ix_campaigns_status'), table_name='campaigns')
    op.drop_table('campaigns')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('segments')
    op.drop_index('ix_leads_tags', table_name='leads')
    op.drop_index(op.f('ix_leads_status'), table_name='leads')
    op.drop_index(op.f('ix_leads_phone'), table_name='leads')
    op.drop_table('leads')
    op.drop_index(op.f('ix_instances_status'), table_name='instances')
    op.drop_table('instances')
    sa.Enum(name='messagestatus').drop(op.get_bind())
    sa.Enum(name='campaignstatus').drop(op.get_bind())
    sa.Enum(name='mediatype').drop(op.get_bind())
    sa.Enum(name='instancestatus').drop(op.get_bind())
    sa.Enum(name='leadstatus').drop(op.get_bind())
    sa.Enum(name='leadsource').drop(op.get_bind())
    sa.Enum(name='userrole').drop(op.get_bind())
