"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: 677f9cb46d91
Create Date: 2026-04-14

Índices para queries críticas:
- messages(lead_id, created_at DESC) — usado pelo webhook para encontrar última mensagem do lead
- messages(lead_id, status) — usado pelo worker para excluir leads já processados no resume
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '677f9cb46d91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Índice composto para webhook: busca última mensagem de um lead por created_at
    op.create_index(
        'ix_messages_lead_created',
        'messages',
        ['lead_id', 'created_at'],
        unique=False,
        postgresql_ops={'created_at': 'DESC NULLS LAST'},
    )

    # Índice composto para o worker no resume: busca leads ainda não enviados
    op.create_index(
        'ix_messages_lead_status',
        'messages',
        ['lead_id', 'status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_messages_lead_status', table_name='messages')
    op.drop_index('ix_messages_lead_created', table_name='messages')
