"""username and webauthn credentials

Revision ID: a7d4e19c2b6f
Revises: 9c1e2f6b7a3d
Create Date: 2026-08-12 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7d4e19c2b6f'
down_revision: Union[str, None] = '9c1e2f6b7a3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.add_column(sa.Column('admin_username', sa.String(), nullable=True))

    op.create_table(
        'webauthn_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('credential_id', sa.String(), nullable=False, unique=True),
        sa.Column('public_key', sa.String(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('webauthn_credentials')
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.drop_column('admin_username')
