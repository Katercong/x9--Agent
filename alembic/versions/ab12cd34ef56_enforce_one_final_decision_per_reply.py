"""enforce one final human review decision per reply

Revision ID: ab12cd34ef56
Revises: 9c7a4d1e2b3f
Create Date: 2026-07-21 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "9c7a4d1e2b3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 当前没有重新审核/版本化流程；唯一索引在 PostgreSQL 和 SQLite 中都能阻止
    # 同一回复通过不同 run 写入相互矛盾的最终人工决定。
    op.create_index(
        "uq_human_review_decisions_reply",
        "human_review_decisions",
        ["inbound_reply_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_human_review_decisions_reply", table_name="human_review_decisions")
