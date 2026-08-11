"""password reset and backup reminder tracking

Revision ID: 9c1e2f6b7a3d
Revises: 71752aaf601f
Create Date: 2026-08-11 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c1e2f6b7a3d'
down_revision: Union[str, None] = '71752aaf601f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.add_column(sa.Column('password_reset_token', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('password_reset_token_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_backup_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.drop_column('last_backup_at')
        batch_op.drop_column('password_reset_token_expires_at')
        batch_op.drop_column('password_reset_token')
