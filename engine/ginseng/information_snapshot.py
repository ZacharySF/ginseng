"""Optional immutable information snapshots, using authorized workspace revisions.

A caller must supply the actual observation timestamp. Effective event dates do
not establish historical availability. Existing records without such captures
remain retrospective; this module does not manufacture a revision history.
"""

from dataclasses import dataclass
from datetime import datetime

from ginseng.finance_models import FinanceWorkspace
from ginseng.provenance import digest


@dataclass(frozen=True)
class InformationSnapshot:
    observed_at: datetime
    revision: int
    payload: bytes
    identity: str

    @classmethod
    def capture(cls, workspace: FinanceWorkspace, observed_at: datetime):
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("Actual timezone-aware observation timestamp required")
        content = workspace.model_dump(mode="json")
        return cls(
            observed_at,
            workspace.revision,
            workspace.model_dump_json().encode(),
            digest(content),
        )

    def workspace(self):
        workspace = FinanceWorkspace.model_validate_json(self.payload)
        if (
            workspace.revision != self.revision
            or digest(workspace.model_dump(mode="json")) != self.identity
        ):
            raise ValueError("Snapshot integrity mismatch")
        return workspace


def information_at(snapshots, cutoff):
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("Timezone-aware information cutoff required")
    available = [s for s in snapshots if s.observed_at <= cutoff]
    if not available:
        raise ValueError(
            "No observed snapshot at this cutoff; current records are retrospective"
        )
    selected = max(available, key=lambda s: (s.observed_at, s.revision))
    return selected.workspace()
